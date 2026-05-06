"""Patch utilities for ROCmForge using stdlib difflib."""

from __future__ import annotations

import difflib
import os
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

    Args:
        migration: Structured edits and new files to apply.
        source_dir: Directory containing the original source files.

    Returns:
        Dict with patch_text, generated_files, and patched_dir.
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

    for edit in migration.edits:
        rel_path = edit.file
        source_path = _resolve_source_path(source_root, rel_path)
        if not source_path.exists():
            print(
                f"[patch_utils] Warning: file not found for edit: {rel_path}",
                file=sys.stderr,
            )
            continue

        state = file_states.get(rel_path)
        if state is None:
            original_text = source_path.read_text(encoding="utf-8", errors="ignore")
            current_text = original_text
        else:
            original_text = state["original"]
            current_text = state["current"]

        if edit.original_block not in current_text:
            print(
                f"[patch_utils] Warning: block not found in {rel_path}",
                file=sys.stderr,
            )
            continue

        updated_text = current_text.replace(edit.original_block, edit.replacement_block, 1)
        file_states[rel_path] = {"original": original_text, "current": updated_text}

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
    }


def _resolve_source_path(source_root: Path, rel_path: str) -> Path:
    rel = Path(rel_path)
    if rel.is_absolute():
        return rel
    return source_root / rel
