"""Run migrated code on the AMD Developer Cloud sandbox via SSH and return metrics."""

import json
import os
import shlex
import shutil
import sys
import time
import tomllib
import uuid
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Environment variable names — set these in .streamlit/secrets.toml or .env
# ---------------------------------------------------------------------------
_ENV_HOST = "AMD_SANDBOX_HOST"
_ENV_USER = "AMD_SANDBOX_USER"
_ENV_KEY_PATH = "AMD_SANDBOX_KEY_PATH"
_ENV_KEY_PASSPHRASE = "AMD_SANDBOX_KEY_PASSPHRASE"
_ENV_CONTAINER = "AMD_SANDBOX_CONTAINER"
_TIMEOUT_DEFAULT = 120


def _get_env(key: str) -> str:
    """Read a required env var; raise clearly if missing."""
    val = _get_config(key)
    if not val:
        raise EnvironmentError(
            f"Environment variable {key!r} is not set. "
            f"Add it to .streamlit/secrets.toml or your .env file."
        )
    return val


def _get_config(key: str, default: str = "") -> str:
    """Read config from env, .env, or Streamlit secrets."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    value = os.environ.get(key, "").strip()
    if value:
        return value

    secrets_path = Path.cwd() / ".streamlit" / "secrets.toml"
    if secrets_path.exists():
        try:
            data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
            value = str(data.get(key, "")).strip()
            if value:
                return value
        except tomllib.TOMLDecodeError as exc:
            raise EnvironmentError(
                f"Could not parse {secrets_path}. For Windows paths in TOML, "
                "use single quotes or escape backslashes, for example "
                r'AMD_SANDBOX_KEY_PATH = "C:\\Users\\noobr\\.ssh\\id_ed25519".'
            ) from exc
        except OSError:
            pass

    try:
        import streamlit as st

        value = str(st.secrets.get(key, "")).strip()
        if value:
            return value
    except Exception:
        pass

    return default


def _mock_result(reason: str) -> dict:
    """Return a mocked result when sandbox env vars are not configured."""
    return {
        "status": "passed",
        "logs": f"[MOCK] AMD sandbox not configured ({reason}). Returning mock result.",
        "runtime_sec": 8.4,
        "gpu_memory_gb": 6.2,
        "exit_code": 0,
        "is_mock": True,
    }


def run_on_amd(
    patched_dir: str,
    entrypoint: str = "app.py",
    timeout_sec: int = _TIMEOUT_DEFAULT,
) -> dict:
    """SCP patched_dir to the AMD sandbox, run the entrypoint, return metrics.

    If AMD_SANDBOX_HOST is not set, falls back to a mock result so local
    development works without a live droplet.

    Returns:
        {status, logs, runtime_sec, gpu_memory_gb, exit_code}
    """
    host = _normalize_host(_get_config(_ENV_HOST))
    if not host:
        return _mock_result("AMD_SANDBOX_HOST not set")
    if _looks_like_placeholder_host(host):
        return _failed(
            "AMD_SANDBOX_HOST still looks like a placeholder. "
            "Use the bare droplet IP, for example 165.245.138.185, not 134.199.x.x."
        )

    local_dir = Path(patched_dir)
    if not local_dir.exists() or not local_dir.is_dir():
        return _failed(f"Patched directory does not exist: {patched_dir}")
    if not (local_dir / entrypoint).exists():
        return _failed(f"Entrypoint not found in patched directory: {entrypoint}")

    user = _get_config(_ENV_USER, "root")
    key_path = _get_config(_ENV_KEY_PATH)
    key_passphrase = _get_config(_ENV_KEY_PASSPHRASE)

    try:
        import paramiko
    except ImportError:
        return _mock_result("paramiko not installed")

    run_id = uuid.uuid4().hex[:12]
    remote_dir = f"/tmp/rocmforge_run_{run_id}"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict = {"hostname": host, "username": user, "timeout": 15}
    if key_path:
        # Load encrypted private key explicitly so we can pass the passphrase.
        if key_passphrase:
            try:
                resolved_key_path = str(Path(key_path).expanduser())
                pkey = None
                last_exc: Exception | None = None
                # Try common key types — DSSKey was removed in newer paramiko.
                loaders = []
                for attr in ("Ed25519Key", "RSAKey", "ECDSAKey", "DSSKey"):
                    if hasattr(paramiko, attr):
                        loaders.append(getattr(paramiko, attr))
                for loader in loaders:
                    try:
                        pkey = loader.from_private_key_file(resolved_key_path, password=key_passphrase)
                        break
                    except Exception as exc:
                        last_exc = exc
                        continue
                if pkey is None:
                    return _failed(f"Could not decrypt SSH key with provided passphrase: {last_exc}")
                connect_kwargs["pkey"] = pkey
            except Exception as exc:
                return _failed(f"Failed to load SSH key: {exc}")
        else:
            connect_kwargs["key_filename"] = str(Path(key_path).expanduser())

    try:
        ssh.connect(**connect_kwargs)
        return _run_remote(
            ssh=ssh,
            patched_dir=patched_dir,
            remote_dir=remote_dir,
            entrypoint=entrypoint,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        return _failed(
            "SSH connection error: "
            f"{_format_ssh_connection_error(exc, key_path=key_path, key_passphrase=key_passphrase)}"
        )
    finally:
        try:
            ssh.close()
        except Exception:
            pass


def _run_remote(
    ssh,
    patched_dir: str,
    remote_dir: str,
    entrypoint: str,
    timeout_sec: int,
) -> dict:
    """Internal: SCP files, run, capture metrics, always clean up."""
    sftp = ssh.open_sftp()
    try:
        _scp_directory(sftp, patched_dir, remote_dir)
    finally:
        sftp.close()

    # Capture GPU memory baseline before run (from idle GPU)
    mem_before = _gpu_memory_gb(ssh)

    container = _get_config(_ENV_CONTAINER, "rocm")
    if container and _container_exists(ssh, container):
        run_cmd = _container_run_command(remote_dir, entrypoint, container)
    else:
        run_cmd = _host_run_command(remote_dir, entrypoint)

    # Run the command while sampling rocm-smi in parallel to capture peak VRAM
    run_result, peak_mem = _peak_gpu_memory_during(ssh, run_cmd, timeout_sec)

    if run_result.get("error"):
        _cleanup_remote(ssh, remote_dir)
        return _failed(f"Remote execution error: {run_result['error']}")

    exit_code = run_result["exit_code"]
    logs = run_result["logs"]

    # Extract runtime from /usr/bin/time output (last line is elapsed seconds)
    runtime_sec = 0.0
    for line in reversed(logs.splitlines()):
        try:
            runtime_sec = float(line.strip())
            break
        except ValueError:
            continue

    # Peak VRAM during run minus the idle baseline gives the run's actual usage.
    # If sampler captured nothing (small/fast script), fall back to peak alone.
    if peak_mem > 0:
        gpu_memory_gb = max(0.0, peak_mem - mem_before)
        if gpu_memory_gb < 0.05:  # very small jobs: just report peak
            gpu_memory_gb = peak_mem
    else:
        gpu_memory_gb = 0.0

    # Always clean up — even on failure
    _cleanup_remote(ssh, remote_dir)

    return {
        "status": "passed" if exit_code == 0 else "failed",
        "logs": logs,
        "runtime_sec": runtime_sec,
        "gpu_memory_gb": round(gpu_memory_gb, 2),
        "exit_code": exit_code,
        "is_mock": False,
    }


def _scp_directory(sftp, local_dir: str, remote_dir: str) -> None:
    """Recursively copy local_dir to remote_dir via SFTP."""
    _sftp_mkdir(sftp, remote_dir)
    for item in Path(local_dir).iterdir():
        if item.name in {".git", ".venv", "__pycache__"}:
            continue
        remote_path = f"{remote_dir}/{item.name}"
        if item.is_file():
            sftp.put(str(item), remote_path)
        elif item.is_dir():
            _scp_directory(sftp, str(item), remote_path)


def _sftp_mkdir(sftp, path: str) -> None:
    """Create remote directory, ignoring if it already exists."""
    try:
        sftp.mkdir(path)
    except IOError:
        pass


def _gpu_memory_gb(ssh) -> float:
    """Query rocm-smi for VRAM used on card0. Returns 0.0 on any failure.

    Tries the rocm container first (where the ROCm tooling lives), then host.
    """
    container = _get_config(_ENV_CONTAINER, "rocm")

    cmds = []
    if container:
        cmds.append(f"docker exec {shlex.quote(container)} rocm-smi --showmeminfo vram --json")
    cmds.append("rocm-smi --showmeminfo vram --json")

    for cmd in cmds:
        try:
            _, stdout, _ = ssh.exec_command(cmd, timeout=10)
            raw = stdout.read().decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            data = json.loads(raw)
            card = next(iter(data.values()))
            # Different rocm-smi versions use different keys
            for key in (
                "VRAM Total Used Memory (B)",
                "VRAM Used Memory (B)",
                "GPU Memory Used (B)",
                "Used Memory (B)",
            ):
                if key in card:
                    return int(card[key]) / (1024 ** 3)
        except Exception:
            continue
    return 0.0


def _peak_gpu_memory_during(ssh, run_cmd: str, timeout_sec: int) -> tuple[dict, float]:
    """Run the command while sampling rocm-smi every 0.5s in parallel.

    Returns (run_result_dict, peak_memory_gb).
    The run_result_dict has the same shape as the existing exec output.
    """
    import threading
    peak = {"gb": 0.0, "stop": False}

    def _sampler():
        while not peak["stop"]:
            mem = _gpu_memory_gb(ssh)
            if mem > peak["gb"]:
                peak["gb"] = mem
            time.sleep(0.5)

    sampler_thread = threading.Thread(target=_sampler, daemon=True)
    sampler_thread.start()
    try:
        _, stdout, stderr = ssh.exec_command(run_cmd, timeout=timeout_sec)
        exit_code = stdout.channel.recv_exit_status()
        logs = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if err:
            logs += f"\nSTDERR:\n{err}"
        return ({"exit_code": exit_code, "logs": logs, "error": None}, peak["gb"])
    except Exception as exc:
        return ({"exit_code": -1, "logs": "", "error": str(exc)}, peak["gb"])
    finally:
        peak["stop"] = True


def _is_encrypted_key_error(exc: Exception) -> bool:
    """Return True for Paramiko/OpenSSH errors caused by a passphrase-protected key."""
    message = str(exc).lower()
    return "private key file is encrypted" in message or (
        "encrypted" in message and "passphrase" in message
    )


def _format_ssh_connection_error(exc: Exception, key_path: str, key_passphrase: str) -> str:
    """Make common SSH configuration failures actionable for the Streamlit report."""
    if key_path and not key_passphrase and _is_encrypted_key_error(exc):
        return (
            f"{exc}. The SSH key at {key_path!r} is passphrase-protected, but "
            f"{_ENV_KEY_PASSPHRASE} is not set. Add the key passphrase to "
            ".streamlit/secrets.toml, Streamlit Cloud secrets, or .env."
        )
    return str(exc)


def _host_run_command(remote_dir: str, entrypoint: str) -> str:
    return f"bash -lc {shlex.quote(_run_shell_body(remote_dir, entrypoint))}"


def _run_shell_body(remote_dir: str, entrypoint: str) -> str:
    """Build the bash script that installs deps and runs the user's entrypoint.

    Strategy: do NOT create a venv. The rocm container already has a fully
    working torch+torchvision+transformers stack. Creating a venv (even with
    --system-site-packages) causes pip to install a CPU-only torch wheel that
    shadows the container's ROCm torch, leading to torch/torchvision version
    mismatches (e.g. `operator torchvision::nms does not exist`).

    Instead we install the user's missing deps directly into the system, but
    skip torch/torchvision/torchaudio/triton (which are already present and
    correctly paired with the ROCm runtime).
    """
    quoted_dir = shlex.quote(remote_dir)
    quoted_entrypoint = shlex.quote(entrypoint)
    return (
        f"cd {quoted_dir} && "
        f"PYTHON_BIN=$(command -v python3 || command -v python) && "

        # Build a filtered requirements file: drop torch/torchvision/torchaudio/triton
        # and relax common pinned deps that conflict with the sandbox.
        f"if [ -f requirements.txt ]; then "
        f"  $PYTHON_BIN -c \""
        f"import re; "
        f"RELAX = {{'pydantic','fastapi','uvicorn','starlette','transformers','tokenizers','accelerate'}}; "
        f"DROP = ('torch','torchvision','torchaudio','triton'); "
        f"lines = open('requirements.txt').readlines(); "
        f"out = []; "
        f"\\n"
        f"def keep(l):\\n"
        f"    s = l.strip().lower()\\n"
        f"    if not s or s.startswith('#') or s.startswith('-'): return True\\n"
        f"    name = re.split(r'[\\s<>=!~;\\[]', s, 1)[0]\\n"
        f"    return not any(name == d for d in DROP)\\n"
        f"\\n"
        f"def relax(l):\\n"
        f"    s = l.strip().lower()\\n"
        f"    if not s or s.startswith('#'): return l\\n"
        f"    name = re.split(r'[\\s<>=!~;\\[]', s, 1)[0]\\n"
        f"    return re.sub(r'==([0-9])', r'>=\\\\1', l) if name in RELAX else l\\n"
        f"\\n"
        f"for l in lines:\\n"
        f"    if keep(l): out.append(relax(l))\\n"
        f"open('requirements-rocm.txt','w').writelines(out)\" 2>/dev/null "
        f"  || (grep -ivE '^[[:space:]]*(torch|torchvision|torchaudio|triton)([[:space:]]|=|<|>|!|~|;|\\[|$)' requirements.txt > requirements-rocm.txt || cp requirements.txt requirements-rocm.txt); "
        f"  $PYTHON_BIN -m pip install --no-cache-dir --quiet --break-system-packages "
        f"    --upgrade-strategy only-if-needed "
        f"    -r requirements-rocm.txt 2>&1 || true; "
        f"fi && "

        # src-layout: if there is a pyproject.toml/setup.py and a src/ dir,
        # install the package itself so imports like `from mypackage.x import`
        # resolve. Fall back to PYTHONPATH=src.
        f"if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]; then "
        f"  if [ -d src ]; then "
        f"    $PYTHON_BIN -m pip install --no-cache-dir --quiet --break-system-packages --no-deps -e . 2>&1 || "
        f"    export PYTHONPATH={quoted_dir}/src:${{PYTHONPATH:-}}; "
        f"  else "
        f"    $PYTHONPATH={quoted_dir}:${{PYTHONPATH:-}}; "
        f"  fi; "
        f"elif [ -d src ]; then "
        f"  export PYTHONPATH={quoted_dir}/src:${{PYTHONPATH:-}}; "
        f"fi && "

        f"export PYTHONPATH={quoted_dir}:{quoted_dir}/src:${{PYTHONPATH:-}} && "
        f"SECONDS=0 && "
        f"$PYTHON_BIN {quoted_entrypoint} 2>&1; "
        f"exit_code=$?; echo $SECONDS; exit $exit_code"
    )


def _container_run_command(remote_dir: str, entrypoint: str, container: str) -> str:
    quoted_container = shlex.quote(container)
    quoted_remote_dir = shlex.quote(remote_dir)
    inner = _run_shell_body(remote_dir, entrypoint)
    return (
        f"docker exec {quoted_container} mkdir -p {quoted_remote_dir} && "
        f"docker cp {quoted_remote_dir}/. {quoted_container}:{quoted_remote_dir} && "
        f"docker exec {quoted_container} bash -lc {shlex.quote(inner)}"
    )


def _container_exists(ssh, container: str) -> bool:
    try:
        cmd = f"docker inspect {shlex.quote(container)} >/dev/null 2>&1; echo $?"
        _, stdout, _ = ssh.exec_command(cmd, timeout=10)
        return stdout.read().decode("utf-8", errors="replace").strip().endswith("0")
    except Exception:
        return False


def _cleanup_remote(ssh, remote_dir: str) -> None:
    """Delete the entire temp run directory on the sandbox."""
    try:
        ssh.exec_command(f"rm -rf {remote_dir}", timeout=15)
    except Exception:
        pass

    container = _get_config(_ENV_CONTAINER, "rocm")
    if container:
        try:
            ssh.exec_command(
                f"docker exec {shlex.quote(container)} rm -rf {shlex.quote(remote_dir)}",
                timeout=15,
            )
        except Exception:
            pass


def _failed(logs: str) -> dict:
    return {
        "status": "failed",
        "logs": logs,
        "runtime_sec": 0.0,
        "gpu_memory_gb": 0.0,
        "exit_code": -1,
        "is_mock": False,
    }


def _normalize_host(value: str) -> str:
    host = value.strip()
    parsed = urlparse(host)
    if parsed.scheme and parsed.hostname:
        return parsed.hostname
    return host


def _looks_like_placeholder_host(host: str) -> bool:
    return ".x" in host.lower() or host.lower().endswith(".x")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m core.benchmark_runner <patched_dir> [entrypoint]")
    patched = sys.argv[1]
    entry = sys.argv[2] if len(sys.argv) > 2 else "app.py"
    result = run_on_amd(patched, entrypoint=entry)
    print(json.dumps(result, indent=2))
