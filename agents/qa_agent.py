"""QA agent: syntax-check migrated code, then run the AMD benchmark runner."""

import ast
from pathlib import Path

from crewai import Agent

from core.benchmark_runner import run_on_amd

qa_agent = Agent(
    role="QA Tester",
    goal="Verify that the migrated code is syntactically valid and would run on AMD hardware",
    backstory="You are a QA engineer who validates GPU code migrations.",
    verbose=False,
    allow_delegation=False,
)


def run_qa(patched_dir: str) -> dict:
    """Syntax-check the patched directory, then run the selected entrypoint."""
    base = Path(patched_dir)
    if not base.exists():
        return _failed(f"Patched directory does not exist: {patched_dir}")

    py_files = sorted(base.rglob("*.py"))
    if not py_files:
        return _failed(f"No .py files found in {patched_dir}")

    syntax_logs = []
    for py_file in py_files:
        relative = py_file.relative_to(base).as_posix()
        try:
            ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError) as exc:
            return _failed(f"Syntax check failed in {relative}: {exc}")
        syntax_logs.append(f"Syntax check passed: {relative}")

    entrypoint = _choose_entrypoint(base, py_files)
    result = run_on_amd(patched_dir, entrypoint=entrypoint)
    result["logs"] = "\n".join(syntax_logs + [result.get("logs", "")]).strip()
    result["entrypoint"] = entrypoint
    result["syntax_checked_files"] = len(py_files)
    return result


def _choose_entrypoint(base: Path, py_files: list[Path]) -> str:
    preferred = ("app.py", "main.py", "run.py")
    root_files = {path.name: path for path in py_files if path.parent == base}
    for name in preferred:
        if name in root_files:
            return name
    return py_files[0].relative_to(base).as_posix()


def _failed(logs: str) -> dict:
    return {
        "status": "failed",
        "logs": logs,
        "runtime_sec": 0.0,
        "gpu_memory_gb": 0.0,
        "exit_code": -1,
        "is_mock": False,
    }
