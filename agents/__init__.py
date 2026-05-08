"""ROCmForge agent orchestrator — single entry point for the Streamlit UI."""

import dataclasses
import json
import os
import tempfile
from pathlib import Path

for _proxy_key in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    if os.environ.get(_proxy_key, "").startswith("http://127.0.0.1:9"):
        os.environ.pop(_proxy_key, None)

if os.name == "nt":
    os.environ["LOCALAPPDATA"] = tempfile.gettempdir()

try:
    import appdirs

    appdirs.user_data_dir = lambda appname=None, *_, **__: str(
        Path(tempfile.gettempdir()) / "CrewAI" / str(appname or "ROCmForge")
    )
except ImportError:
    pass

from core.pattern_scanner import scan
from core.scoring import score_before, score_after
from agents.migration_agent import run_migration_agent
from agents.qa_agent import run_qa
from agents.report_agent import build_report

_TARGET_FILENAMES = {"dockerfile", "requirements.txt"}
_MAX_QA_RETRIES = 2


def _read_source_files(input_path: str) -> dict[str, str]:
    """Read all scannable files from input_path into {filename: content}."""
    base = Path(input_path)
    source_files: dict[str, str] = {}

    def _source_key(file_path: Path, root_path: Path) -> str:
        return file_path.relative_to(root_path).as_posix()

    if base.is_file():
        source_files[_source_key(base, base.parent)] = base.read_text(encoding="utf-8", errors="ignore")
        return source_files
    for f in base.rglob("*"):
        if not f.is_file():
            continue
        name_lower = f.name.lower()
        if (
            f.suffix == ".py"
            or name_lower in _TARGET_FILENAMES
            or name_lower.startswith("readme")
        ):
            try:
                source_files[_source_key(f, base)] = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
    return source_files


def run_migration(input_path: str) -> dict:
    """Run the full ROCmForge migration pipeline.

    Args:
        input_path: Path to a directory or single .py file to migrate.

    Returns:
        A results dict consumed by the Streamlit UI with keys:
        issues, patch_text, generated_files, qa_result,
        score_before, score_after, report_markdown, attempts.
    """
    # 1. Scan for CUDA/NVIDIA issues
    issues = scan(input_path)
    issues_dicts = [dataclasses.asdict(i) for i in issues]

    # 2. Read source files for the migration agent
    source_files = _read_source_files(input_path)

    # 3-4. Generate a patch and QA it. If QA fails, feed the logs back to the
    # migration agent for up to two correction attempts.
    attempts = []
    migration_result: dict = {}
    qa_result: dict = {}
    qa_feedback = ""
    issues_json = json.dumps(issues_dicts)

    for attempt_number in range(1, _MAX_QA_RETRIES + 2):
        migration_result = run_migration_agent(
            issues_json=issues_json,
            source_files=source_files,
            qa_feedback=qa_feedback,
        )

        patched_dir = migration_result.get("patched_dir", "")
        qa_result = run_qa(patched_dir) if patched_dir else {
            "status": "failed",
            "logs": "No patched directory produced by migration agent.",
            "runtime_sec": 0.0,
            "gpu_memory_gb": 0.0,
            "exit_code": -1,
        }

        attempts.append(
            {
                "attempt": attempt_number,
                "patch": migration_result.get("patch_text", ""),
                "qa_result": qa_result,
                "commentary": migration_result.get("commentary", ""),
                "edits_raw": migration_result.get("edits_raw", []),
            }
        )

        if qa_result.get("status") != "failed":
            break

        qa_feedback = str(qa_result.get("logs", ""))

    # 5. Score before and after
    sb = score_before(issues)
    sa = score_after([], qa_result)

    # 6. Build report
    report_markdown = build_report(
        issues=issues_dicts,
        patch_text=migration_result.get("patch_text", ""),
        generated_files=migration_result.get("generated_files", {}),
        qa_result=qa_result,
        score_before=sb,
        score_after=sa,
        commentary=migration_result.get("commentary", ""),
    )

    return {
        "issues": issues_dicts,
        "patch_text": migration_result.get("patch_text", ""),
        "generated_files": migration_result.get("generated_files", {}),
        "qa_result": qa_result,
        "score_before": sb,
        "score_after": sa,
        "report_markdown": report_markdown,
        "attempts": attempts,
    }
