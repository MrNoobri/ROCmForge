"""QA agent — syntax-checks the migrated code (mocked AMD run for Phase 6)."""

import ast
from pathlib import Path

from crewai import Agent

qa_agent = Agent(
    role="QA Tester",
    goal="Verify that the migrated code is syntactically valid and would run on AMD hardware",
    backstory="You are a QA engineer who validates GPU code migrations.",
    verbose=False,
    allow_delegation=False,
)


def run_qa(patched_dir: str) -> dict:
    """Syntax-check the patched directory. Returns a result dict.

    Phase 8 replaces this with a real AMD sandbox run via benchmark_runner.py.
    """
    base = Path(patched_dir)
    target = base / "app.py"
    if not target.exists():
        py_files = list(base.glob("*.py"))
        if not py_files:
            return {
                "status": "failed",
                "logs": f"No .py files found in {patched_dir}",
                "runtime_sec": 0.0,
                "gpu_memory_gb": 0.0,
            }
        target = py_files[0]

    try:
        ast.parse(target.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError) as exc:
        return {
            "status": "failed",
            "logs": str(exc),
            "runtime_sec": 0.0,
            "gpu_memory_gb": 0.0,
        }

    return {
        "status": "passed",
        "logs": "Syntax check passed.",
        "runtime_sec": 8.4,
        "gpu_memory_gb": 6.2,
    }
