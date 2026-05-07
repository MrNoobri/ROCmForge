"""Load a local directory or GitHub URL into a temp directory for scanning."""

import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse


def load_repo(input_path_or_url: str) -> str:
    """Return a local directory path containing the code to scan.

    Accepts:
    - A local directory path  → returned as-is after validation
    - A local .py file path   → returned as-is after validation
    - A GitHub URL            → cloned into a temp directory, temp path returned

    The caller is responsible for cleaning up temp directories when done.
    Returns the path as a string.
    """
    stripped = input_path_or_url.strip()

    if _is_github_url(stripped):
        return _clone_github(stripped)

    path = Path(stripped)
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {stripped}")
    return str(path.resolve())


def load_repo_from_url(url: str) -> tuple[str, str]:
    """Load a GitHub URL and return (input_path, temp_path) for app.py cleanup."""
    path = load_repo(url)
    return path, path


def _is_github_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and "github.com" in parsed.netloc
    except Exception:
        return False


def _clone_github(url: str) -> str:
    """Clone a GitHub repo into a temp directory and return the path."""
    try:
        import git
    except ImportError:
        raise ImportError(
            "gitpython is required for GitHub URL support. "
            "Run: pip install gitpython"
        )

    # Normalise URL — strip trailing slashes and .git suffix ambiguity
    clone_url = url.rstrip("/")
    if not clone_url.endswith(".git"):
        clone_url += ".git"

    tmp_dir = tempfile.mkdtemp(prefix="rocmforge_repo_")
    try:
        print(f"Cloning {url} into {tmp_dir} ...")
        git.Repo.clone_from(clone_url, tmp_dir, depth=1)
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone {url}: {exc}") from exc

    return tmp_dir


def cleanup_temp(path: str) -> None:
    """Delete a temp directory created by load_repo. Safe to call on non-temp paths —
    only deletes if path is inside the system temp dir."""
    tmp_root = Path(tempfile.gettempdir())
    target = Path(path)
    if tmp_root in target.parents:
        shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m core.repo_loader <path-or-github-url>")
    result = load_repo(sys.argv[1])
    print(f"Loaded: {result}")
