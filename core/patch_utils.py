"""Patch utilities for ROCmForge using stdlib difflib."""

from __future__ import annotations

import difflib
import re
import shutil
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field


class Edit(BaseModel):
    file: str
    original_block: str
    replacement_block: str
    rationale: str


class MigrationOutput(BaseModel):
    edits: list[Edit] = Field(default_factory=list)
    new_files: dict[str, str] = Field(default_factory=dict)
    commentary: str = ""


def apply_edits(migration: MigrationOutput, source_dir: str) -> dict:
    """Apply MigrationOutput edits to a source directory and return a unified diff.

    Each edit is tried as an exact match first, then with whitespace-normalised
    matching as a fallback. Edits that cannot be applied are returned in
    `skipped_edits` so the orchestrator can surface them and feed them back to
    the LLM on retry.

    Args:
        migration: Structured edits and new files to apply.
        source_dir: Directory containing the original source files.

    Returns:
        Dict with patch_text, generated_files, patched_dir, applied_edits,
        skipped_edits.
    """
    source_root = Path(source_dir)
    patched_root = Path(tempfile.mkdtemp(prefix="rocmforge_patch_"))

    if source_root.exists():
        if source_root.is_dir():
            shutil.copytree(source_root, patched_root, dirs_exist_ok=True)
        elif source_root.is_file():
            target = patched_root / source_root.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root, target)
    else:
        print(f"[patch_utils] Warning: source_dir not found: {source_dir}", file=sys.stderr)

    file_states: dict[str, dict[str, str]] = {}
    applied_edits: list[dict] = []
    skipped_edits: list[dict] = []

    for edit in migration.edits:
        rel_path = edit.file
        source_path = _resolve_source_path(source_root, rel_path)
        if not source_path.exists():
            skipped_edits.append(
                {
                    "file": rel_path,
                    "original_block": edit.original_block,
                    "replacement_block": edit.replacement_block,
                    "rationale": edit.rationale,
                    "reason": "file_not_found",
                    "detail": f"File {rel_path} not present in source workspace.",
                }
            )
            continue

        state = file_states.get(rel_path)
        if state is None:
            original_text = source_path.read_text(encoding="utf-8", errors="ignore")
            current_text = original_text
        else:
            original_text = state["original"]
            current_text = state["current"]

        if edit.original_block == edit.replacement_block:
            skipped_edits.append(
                {
                    "file": rel_path,
                    "original_block": edit.original_block,
                    "replacement_block": edit.replacement_block,
                    "rationale": edit.rationale,
                    "reason": "no_op",
                    "detail": "Original and replacement blocks are identical.",
                }
            )
            continue

        replaced, updated_text, match_kind = _try_replace(current_text, edit)
        if not replaced:
            already_applied = (
                edit.replacement_block.strip()
                and edit.replacement_block in current_text
            )
            skipped_edits.append(
                {
                    "file": rel_path,
                    "original_block": edit.original_block,
                    "replacement_block": edit.replacement_block,
                    "rationale": edit.rationale,
                    "reason": "already_applied" if already_applied else "block_not_found",
                    "detail": (
                        "Replacement already present in file."
                        if already_applied
                        else "original_block did not match the file (after exact and whitespace-normalised comparison)."
                    ),
                }
            )
            continue

        file_states[rel_path] = {"original": original_text, "current": updated_text}
        applied_edits.append(
            {
                "file": rel_path,
                "original_block": edit.original_block,
                "replacement_block": edit.replacement_block,
                "rationale": edit.rationale,
                "match": match_kind,
            }
        )

    for rel_path, contents in migration.new_files.items():
        file_states.setdefault(rel_path, {"original": "", "current": contents})

    for rel_path, state in file_states.items():
        target_path = patched_root / Path(rel_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(state["current"], encoding="utf-8")

    diff_chunks: list[str] = []
    for rel_path, state in file_states.items():
        original_lines = state["original"].splitlines(keepends=True)
        new_lines = state["current"].splitlines(keepends=True)
        if original_lines == new_lines:
            continue
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=rel_path,
            tofile=rel_path,
            lineterm="",
        )
        diff_text = "\n".join(diff)
        if diff_text:
            diff_chunks.append(diff_text)

    patch_text = "\n\n".join(diff_chunks)
    return {
        "patch_text": patch_text,
        "generated_files": migration.new_files,
        "patched_dir": str(patched_root),
        "applied_edits": applied_edits,
        "skipped_edits": skipped_edits,
    }


def _try_replace(current_text: str, edit: Edit) -> tuple[bool, str, str]:
    """Try to apply edit to text. Returns (replaced, new_text, match_kind)."""
    if edit.original_block in current_text:
        return True, current_text.replace(edit.original_block, edit.replacement_block, 1), "exact"

    pattern = _whitespace_tolerant_pattern(edit.original_block)
    if pattern is None:
        return False, current_text, ""
    match = pattern.search(current_text)
    if not match:
        return False, current_text, ""

    new_text = current_text[: match.start()] + edit.replacement_block + current_text[match.end():]
    return True, new_text, "whitespace_normalised"


def _whitespace_tolerant_pattern(block: str) -> re.Pattern[str] | None:
    """Build a regex matching `block` with flexible internal whitespace.

    Trailing/leading whitespace on each line is normalised so the LLM can supply
    a slightly mis-indented original_block and still match.
    """
    if not block.strip():
        return None
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return None
    parts = [re.escape(line) for line in lines]
    pattern_text = r"\s*\n\s*".join(parts)
    pattern_text = r"[ \t]*" + pattern_text + r"[ \t]*"
    try:
        return re.compile(pattern_text)
    except re.error:
        return None


def _resolve_source_path(source_root: Path, rel_path: str) -> Path:
    rel = Path(rel_path)
    if rel.is_absolute():
        return rel
    return source_root / rel
