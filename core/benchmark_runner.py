"""Run migrated code on the AMD Developer Cloud sandbox via SSH and return metrics."""

import json
import os
import shlex
import shutil
import sys
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

    secrets_path = Path(".streamlit") / "secrets.toml"
    if secrets_path.exists():
        try:
            data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
            value = str(data.get(key, "")).strip()
            if value:
                return value
        except Exception:
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
                for loader in (
                    paramiko.Ed25519Key,
                    paramiko.RSAKey,
                    paramiko.ECDSAKey,
                    paramiko.DSSKey,
                ):
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
        return _failed(f"SSH connection error: {exc}")
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

    # Capture GPU memory before run
    mem_before = _gpu_memory_gb(ssh)

    container = _get_config(_ENV_CONTAINER, "rocm")
    if container and _container_exists(ssh, container):
        run_cmd = _container_run_command(remote_dir, entrypoint, container)
    else:
        run_cmd = _host_run_command(remote_dir, entrypoint)

    try:
        _, stdout, stderr = ssh.exec_command(run_cmd, timeout=timeout_sec)
        exit_code = stdout.channel.recv_exit_status()
        logs = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if err:
            logs += f"\nSTDERR:\n{err}"
    except Exception as exc:
        _cleanup_remote(ssh, remote_dir)
        return _failed(f"Remote execution error: {exc}")

    # Extract runtime from /usr/bin/time output (last line is elapsed seconds)
    runtime_sec = 0.0
    for line in reversed(logs.splitlines()):
        try:
            runtime_sec = float(line.strip())
            break
        except ValueError:
            continue

    mem_after = _gpu_memory_gb(ssh)
    gpu_memory_gb = max(0.0, mem_after - mem_before)

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
    """Query rocm-smi for VRAM used on card0. Returns 0.0 on any failure."""
    try:
        _, stdout, _ = ssh.exec_command("rocm-smi --showmeminfo vram --json", timeout=10)
        raw = stdout.read().decode("utf-8", errors="replace").strip()
        data = json.loads(raw)
        card = next(iter(data.values()))  # first GPU
        used_bytes = int(card.get("VRAM Total Used Memory (B)", 0))
        return used_bytes / (1024 ** 3)
    except Exception:
        return 0.0


def _host_run_command(remote_dir: str, entrypoint: str) -> str:
    return f"bash -lc {shlex.quote(_run_shell_body(remote_dir, entrypoint))}"


def _run_shell_body(remote_dir: str, entrypoint: str) -> str:
    quoted_dir = shlex.quote(remote_dir)
    quoted_entrypoint = shlex.quote(entrypoint)
    return (
        # Set up the working directory and Python binary.
        f"cd {quoted_dir} && "
        f"PYTHON_BIN=$(command -v python3 || command -v python) && "
        f"$PYTHON_BIN -m venv --system-site-packages .venv && "

        # Relax exact-pinned versions that commonly conflict with sandbox libs.
        # We generate requirements-rocm.txt with >= bounds so pip can resolve
        # upward instead of downgrading system packages.
        f"if [ -f requirements.txt ]; then "
        f"  python3 -c \""
        f"import re, sys; "
        f"RELAX = {{'pydantic','fastapi','uvicorn','starlette','transformers','tokenizers','accelerate','triton'}}; "
        f"lines = open('requirements.txt').readlines(); "
        f"out = []; "
        f"[out.append(re.sub(r'==([0-9])', r'>=\\1', l) if any(l.lower().startswith(p) for p in RELAX) else l) for l in lines]; "
        f"open('requirements-rocm.txt','w').writelines(out)"
        f"\" 2>/dev/null || cp requirements.txt requirements-rocm.txt; "
        f".venv/bin/pip install --no-cache-dir --quiet "
        f"--upgrade-strategy only-if-needed "
        f"-r requirements-rocm.txt 2>&1 || true; "
        f"fi && "

        # src-layout: if there is a pyproject.toml/setup.py and a src/ dir,
        # install the package itself so imports like `from mypackage.x import`
        # resolve correctly. Fall back to setting PYTHONPATH=src.
        f"if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]; then "
        f"  if [ -d src ]; then "
        f"    .venv/bin/pip install --no-cache-dir --quiet -e . 2>&1 || "
        f"    export PYTHONPATH={quoted_dir}/src:${{PYTHONPATH:-}}; "
        f"  else "
        f"    .venv/bin/pip install --no-cache-dir --quiet -e . 2>&1 || true; "
        f"  fi; "
        f"elif [ -d src ]; then "
        f"  export PYTHONPATH={quoted_dir}/src:${{PYTHONPATH:-}}; "
        f"fi && "

        f"SECONDS=0 && "
        f".venv/bin/python {quoted_entrypoint} 2>&1; "
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
