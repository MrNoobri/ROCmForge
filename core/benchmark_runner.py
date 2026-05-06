"""Run migrated code on the AMD Developer Cloud sandbox via SSH and return metrics."""

import json
import os
import shutil
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment variable names — set these in .streamlit/secrets.toml or .env
# ---------------------------------------------------------------------------
_ENV_HOST = "AMD_SANDBOX_HOST"
_ENV_USER = "AMD_SANDBOX_USER"
_ENV_KEY_PATH = "AMD_SANDBOX_KEY_PATH"
_TIMEOUT_DEFAULT = 120


def _get_env(key: str) -> str:
    """Read a required env var; raise clearly if missing."""
    val = os.environ.get(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Environment variable {key!r} is not set. "
            f"Add it to .streamlit/secrets.toml or your .env file."
        )
    return val


def _mock_result(reason: str) -> dict:
    """Return a mocked result when sandbox env vars are not configured."""
    return {
        "status": "passed",
        "logs": f"[MOCK] AMD sandbox not configured ({reason}). Returning mock result.",
        "runtime_sec": 8.4,
        "gpu_memory_gb": 6.2,
        "exit_code": 0,
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
    host = os.environ.get(_ENV_HOST, "").strip()
    if not host:
        return _mock_result("AMD_SANDBOX_HOST not set")

    user = os.environ.get(_ENV_USER, "root").strip()
    key_path = os.environ.get(_ENV_KEY_PATH, "").strip()

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
        connect_kwargs["key_filename"] = key_path

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
        return {
            "status": "failed",
            "logs": f"SSH connection error: {exc}",
            "runtime_sec": 0.0,
            "gpu_memory_gb": 0.0,
            "exit_code": -1,
        }
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
    import paramiko

    sftp = ssh.open_sftp()
    try:
        _scp_directory(sftp, patched_dir, remote_dir)
    finally:
        sftp.close()

    # Capture GPU memory before run
    mem_before = _gpu_memory_gb(ssh)

    # Build the remote run command inside a fresh per-run venv
    run_cmd = (
        f"cd {remote_dir} && "
        f"python -m venv .venv && "
        f".venv/bin/pip install --no-cache-dir --quiet -r requirements.txt 2>&1 && "
        f"/usr/bin/time -f '%e' .venv/bin/python {entrypoint} 2>&1"
    )

    stdin, stdout, stderr = ssh.exec_command(run_cmd, timeout=timeout_sec)
    exit_code = stdout.channel.recv_exit_status()
    logs = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        logs += f"\nSTDERR:\n{err}"

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
    }


def _scp_directory(sftp, local_dir: str, remote_dir: str) -> None:
    """Recursively copy local_dir to remote_dir via SFTP."""
    _sftp_mkdir(sftp, remote_dir)
    for item in Path(local_dir).iterdir():
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


def _cleanup_remote(ssh, remote_dir: str) -> None:
    """Delete the entire temp run directory on the sandbox."""
    try:
        ssh.exec_command(f"rm -rf {remote_dir}", timeout=15)
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m core.benchmark_runner <patched_dir> [entrypoint]")
    patched = sys.argv[1]
    entry = sys.argv[2] if len(sys.argv) > 2 else "app.py"
    result = run_on_amd(patched, entrypoint=entry)
    print(json.dumps(result, indent=2))
