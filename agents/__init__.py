"""ROCmForge agent orchestrator — single entry point for the Streamlit UI."""

import dataclasses
import json
import os
from pathlib import Path

from core.pattern_scanner import scan
from core.scoring import score_before, score_after
from agents.migration_agent import run_migration_agent
from agents.qa_agent import run_qa
from agents.report_agent import build_report

_TARGET_FILENAMES = {"dockerfile", "requirements.txt"}


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

    # 3. Run migration agent (produces patch + generated files)
    migration_result = run_migration_agent(
        issues_json=json.dumps(issues_dicts),
        source_files=source_files,
    )

    # 4. QA check on the patched directory
    patched_dir = migration_result.get("patched_dir", "")
    qa_result = run_qa(patched_dir) if patched_dir else {
        "status": "failed",
        "logs": "No patched directory produced by migration agent.",
        "runtime_sec": 0.0,
        "gpu_memory_gb": 0.0,
    }

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
        "attempts": [
            {
                "patch": migration_result.get("patch_text", ""),
                "qa_result": qa_result,
            }
        ],
    }
