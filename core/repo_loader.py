"""Load a local directory, Python file, or GitHub URL for scanning."""

import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse


def load_repo(input_path_or_url: str) -> str:
    """Return a local path containing code to scan.

    Accepts a local directory, a local Python file, or a GitHub URL. GitHub
    repositories are cloned into a temporary directory.
    """
    stripped = input_path_or_url.strip()

    if _is_github_url(stripped):
        return _clone_github(stripped)

    path = Path(stripped)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {stripped}")
    return str(path.resolve())


def load_repo_from_url(url: str) -> tuple[str, str]:
    """Load a GitHub URL and return (input_path, temp_path) for app.py.

    The second value should be passed to cleanup_temp() when the caller is done.
    """
    path = load_repo(url)
    return path, path


def cleanup_temp(path: str) -> None:
    """Delete temp directories created by load_repo(), ignoring non-temp paths."""
    tmp_root = Path(tempfile.gettempdir()).resolve()
    target = Path(path).resolve()
    if tmp_root == target or tmp_root in target.parents:
        shutil.rmtree(target, ignore_errors=True)


def _is_github_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() == "github.com"


def _clone_github(url: str) -> str:
    try:
        import git
    except ImportError as exc:
        raise ImportError(
            "gitpython is required for GitHub URL support. "
            "Run: python -m pip install -r requirements.txt"
        ) from exc

    clone_url = url.rstrip("/")
    if not clone_url.endswith(".git"):
        clone_url += ".git"

    tmp_dir = tempfile.mkdtemp(prefix="rocmforge_repo_")
    try:
        git.Repo.clone_from(clone_url, tmp_dir, depth=1)
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone {url}: {exc}") from exc

    return tmp_dir
