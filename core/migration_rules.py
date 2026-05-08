
"""Deterministic pattern->edit registry for ROCmForge migration.

This module is the *primary* fix path. Each rule converts a known scanner or
runtime pattern into one or more `Edit` objects, applied before the LLM is
consulted. The LLM is then asked only to handle whatever the registry could not
mechanically solve — the safety net becomes the foundation.

Adding a new rule:
    1. Add a scanner pattern in core.pattern_scanner (if it's a static pattern).
    2. Add a function below following the `RuleFn` signature.
    3. Register it in `RULES`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Callable

from core.patch_utils import Edit


# A rule sees the issue, all source files, and the running edit list (so it can
# avoid duplicating edits other rules already produced). It returns 0..N edits.
RuleFn = Callable[[dict, dict[str, str], list[Edit]], list[Edit]]


_DEVICE_DEF = 'device = torch.device("cuda" if torch.cuda.is_available() else "cpu")'


def apply_rules(
    issues: Iterable[dict],
    source_files: dict[str, str],
) -> tuple[list[Edit], list[dict]]:
    """Run every registered rule against every issue.

    Issue file paths may be absolute (from the scanner walking a temp dir) or
    relative (from source_files keys). We normalise each issue's file to match
    the source_files key before invoking rules.

    Returns:
        (edits, handled_issues) — edits to apply, and the subset of issues a
        rule produced output for. Issues not in `handled_issues` are passed to
        the LLM for free-form handling.
    """
    edits: list[Edit] = []
    handled: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    issue_list = [_normalise_issue_file(issue, source_files) for issue in issues]

    for issue in issue_list:
        pattern_id = str(issue.get("pattern_id", ""))
        rule = RULES.get(pattern_id)
        if rule is None:
            continue
        produced = rule(issue, source_files, edits)
        appended_any = False
        for edit in produced:
            key = (edit.file, edit.original_block)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            edits.append(edit)
            appended_any = True
        if appended_any:
            handled.append(issue)

    edits.extend(_global_post_edits(issue_list, source_files, edits, seen_keys))
    return edits, handled


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------


def _normalise_issue_file(issue: dict, source_files: dict[str, str]) -> dict:
    """Return a copy of `issue` whose `file` matches a key in source_files.

    The scanner stamps issues with the absolute path it walked, while
    source_files is keyed by the path relative to the input root. This bridges
    the two by trying: exact match, posix-normalised match, suffix match, and
    finally basename match.
    """
    raw = str(issue.get("file", ""))
    if not raw or raw in source_files:
        return issue

    posix = raw.replace("\\", "/")
    if posix in source_files:
        return {**issue, "file": posix}

    # Suffix match: the issue path ends with a known source key.
    for key in source_files:
        if posix.endswith("/" + key) or posix.endswith(key):
            return {**issue, "file": key}

    # Basename fallback (works for single-file inputs).
    base = posix.rsplit("/", 1)[-1]
    if base in source_files:
        return {**issue, "file": base}

    return issue


def _line_at(content: str, line_no: int) -> tuple[str, str]:
    """Return (full_line_with_indent, indent) for a 1-based line number."""
    if line_no <= 0:
        return "", ""
    lines = content.splitlines()
    if line_no - 1 >= len(lines):
        return "", ""
    line = lines[line_no - 1]
    indent = line[: len(line) - len(line.lstrip())]
    return line, indent


def _is_py(filename: str) -> bool:
    return filename.lower().endswith(".py")


def _file_lines(source_files: dict[str, str], filename: str, line_no: int) -> tuple[str, str, str]:
    content = source_files.get(filename, "")
    line, indent = _line_at(content, line_no)
    return content, line, indent


def _commented(line: str, note: str) -> str:
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}# {note}: {line.lstrip()}"


# ---------------------------------------------------------------------------
# Static pattern rules
# ---------------------------------------------------------------------------


def _rule_import_bitsandbytes(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    edits: list[Edit] = []
    for line in source_files[filename].splitlines():
        stripped = line.strip()
        if (
            stripped == "import bitsandbytes"
            or stripped.startswith("import bitsandbytes as ")
            or stripped.startswith("from bitsandbytes ")
        ):
            edits.append(
                Edit(
                    file=filename,
                    original_block=line,
                    replacement_block=_commented(line, "Removed CUDA-only bitsandbytes import for ROCm"),
                    rationale="bitsandbytes is CUDA-only; remove import so ROCm runtime does not fail.",
                )
            )
    return edits


def _rule_hf_bitsandbytes_quant(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    content, line, indent = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    stripped = line.strip()

    if re.match(r"^\s*load_in_(?:4bit|8bit)\s*=\s*True\s*,?\s*$", line):
        replacement = f"{indent}# Removed bitsandbytes quantization for ROCm: {stripped}"
    else:
        replacement = re.sub(r",?\s*load_in_(?:4bit|8bit)\s*=\s*True", "", line)
        replacement = re.sub(r"\bdevice_map\s*=\s*['\"]cuda['\"]", 'device_map="auto"', replacement)
        if replacement == line:
            return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="bitsandbytes 4/8-bit quantization is CUDA-only; remove the flag (use Optimum-AMD/AutoGPTQ on ROCm).",
        )
    ]


def _rule_device_map_cuda(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = re.sub(r"\bdevice_map\s*=\s*['\"]cuda['\"]", 'device_map="auto"', line)
    if replacement == line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale='device_map="cuda" pins HF dispatch to CUDA; "auto" lets Accelerate target ROCm.',
        )
    ]


def _rule_hardcoded_gpu(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, indent = _file_lines(source_files, filename, line_no)
    if not line or "torch.cuda.set_device" not in line:
        return []
    # If the line is inside a function/class, replace it with a comment and
    # rely on the global post-pass to add a module-level `device =`.
    if indent:
        return [
            Edit(
                file=filename,
                original_block=line,
                replacement_block=f"{indent}# Replaced hardcoded device select; module-level `device` is used instead.",
                rationale="Comment out hardcoded torch.cuda.set_device() inside a function; module-level device handles selection.",
            )
        ]
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=f"{indent}{_DEVICE_DEF}",
            rationale="Replace hardcoded torch.cuda.set_device() with portable device detection.",
        )
    ]


def _rule_cuda_home_ref(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line or "CUDA_HOME" not in line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=_commented(line, "Removed CUDA_HOME for ROCm portability"),
            rationale="CUDA_HOME forces the CUDA toolkit path; ROCm uses ROCM_PATH.",
        )
    ]


def _rule_cuda_visible_devices(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = re.sub(
        r'(["\'])CUDA_VISIBLE_DEVICES\1',
        r'\1HIP_VISIBLE_DEVICES\1',
        line,
    )
    if replacement == line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="ROCm honours HIP_VISIBLE_DEVICES (and ROCR_VISIBLE_DEVICES) instead of CUDA_VISIBLE_DEVICES.",
        )
    ]


def _rule_nvidia_smi_subprocess(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    content, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []

    block = _gather_subprocess_block(content, line_no)
    if block is None:
        replacement = _commented(line, "Removed nvidia-smi/nvcc subprocess call for ROCm")
        return [
            Edit(
                file=filename,
                original_block=line,
                replacement_block=replacement,
                rationale="nvidia-smi/nvcc are not present on ROCm hosts; remove or replace with rocm-smi.",
            )
        ]

    original_block, _ = block
    block_lines = original_block.splitlines()
    first_line = block_lines[0]
    block_indent = first_line[: len(first_line) - len(first_line.lstrip())]

    # Detect `var = subprocess...` so the no-op shim binds the same name.
    var_match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*subprocess\.", first_line)
    var_name = var_match.group(1) if var_match else "_rocmforge_nvidia_smi_result"

    commented = "\n".join(
        f"{block_indent}# (ROCm) {ln.lstrip()}" if ln.strip() else ln
        for ln in block_lines
    )
    replacement = (
        commented
        + f'\n{block_indent}# Replaced with a portable shim; use shutil.which("rocm-smi") for AMD hosts.'
        + f"\n{block_indent}{var_name} = type('Result', (), {{'returncode': 1, 'stdout': '', 'stderr': 'nvidia-smi unavailable on ROCm host'}})()"
    )
    return [
        Edit(
            file=filename,
            original_block=original_block,
            replacement_block=replacement,
            rationale="Comment out the CUDA-only nvidia-smi/nvcc subprocess and substitute a no-op result so callers do not crash on ROCm.",
        )
    ]


def _gather_subprocess_block(content: str, start_line: int) -> tuple[str, int] | None:
    """Return the multi-line ``result = subprocess.run(...)`` block, or None.

    `start_line` is the 1-based line where the scanner found the match. We walk
    forward until parentheses balance.
    """
    lines = content.splitlines()
    if start_line <= 0 or start_line - 1 >= len(lines):
        return None

    # find the actual start: walk back to the line containing `subprocess.`
    idx = start_line - 1
    while idx >= 0 and "subprocess." not in lines[idx]:
        idx -= 1
    if idx < 0:
        return None

    open_count = 0
    end_idx = idx
    started = False
    for i in range(idx, len(lines)):
        for ch in lines[i]:
            if ch == "(":
                open_count += 1
                started = True
            elif ch == ")":
                open_count -= 1
        end_idx = i
        if started and open_count <= 0:
            break

    block_lines = lines[idx : end_idx + 1]
    if not block_lines:
        return None
    return "\n".join(block_lines), idx + 1


def _rule_to_cuda_string(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = re.sub(
        r'\.to\(\s*["\']cuda(?::\d+)?["\']\s*([\),])',
        r".to(device\1",
        line,
    )
    if replacement == line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale='Replace .to("cuda") with .to(device) so ROCm/CPU fallbacks work.',
        )
    ]


def _rule_device_string_cuda(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = re.sub(
        r"""(?x)
        (?P<lhs>\b(?:device|DEVICE|self\.device)\s*=\s*)
        (?:torch\.device\s*\(\s*)?
        ['\"]cuda(?::\d+)?['\"]
        (?:\s*\))?
        """,
        r'\g<lhs>torch.device("cuda" if torch.cuda.is_available() else "cpu")',
        line,
    )
    if replacement == line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale='Hardcoded device="cuda" prevents ROCm/CPU fallback; use torch.cuda.is_available().',
        )
    ]


_CUDA_CALL_RE = re.compile(r"\.cuda\((?P<args>[^()]*)\)")


def _rule_pytorch_cuda_method(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    content, line, indent = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    # Skip torch.cuda.<something>() calls (e.g. torch.cuda.synchronize) — those
    # are portable on ROCm because torch maps the cuda namespace to HIP.
    cuda_match = _CUDA_CALL_RE.search(line)
    if not cuda_match or "torch.cuda." in line:
        return []

    stripped = line.strip()
    hf_models = _hf_model_variables(content)
    var_match = re.match(r"(?P<var>[A-Za-z_][A-Za-z0-9_\.]*)\.cuda\(", stripped)
    is_hf_dispatched = (
        var_match
        and var_match.group("var") in hf_models
        and "device_map" in content
    )

    if is_hf_dispatched:
        replacement = f"{indent}# Removed {stripped}; HF device_map dispatches with Accelerate hooks."
    else:
        # Preserve any arguments to .cuda() (e.g. non_blocking=True).
        args = cuda_match.group("args").strip()
        if args:
            new_call = f".to(device, {args})"
        else:
            new_call = ".to(device)"
        replacement = line[: cuda_match.start()] + new_call + line[cuda_match.end():]
        if replacement == line:
            return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="Replace direct .cuda(...) with .to(device, ...); skip when HF Accelerate dispatches the model.",
        )
    ]


def _rule_dep_cuda_only(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = f"# Removed CUDA-only dependency for ROCm review: {line.strip()}"
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="CUDA-only dependency; flag for ROCm-compatible replacement.",
        )
    ]


def _rule_dep_pinned_version_conflict(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line or "==" not in line:
        return []
    replacement = re.sub(r"==(\d)", r">=\1", line)
    if replacement == line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="Relax exact pin to >= so the ROCm sandbox's pre-installed newer version is accepted.",
        )
    ]


def _rule_dep_torch_cuda_wheel(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = (
        f"# {line.strip()}  (replaced for ROCm)\n"
        "--extra-index-url https://download.pytorch.org/whl/rocm6.1\n"
        f"{re.sub(r'\\+cu\\d{2,3}', '', line.strip())}"
    )
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="Swap CUDA-pinned PyTorch wheel for the ROCm wheel index.",
        )
    ]


def _rule_docker_nvidia_base(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block="FROM rocm/pytorch:latest",
            rationale="Replace NVIDIA CUDA base image with a ROCm PyTorch base image.",
        )
    ]


def _rule_docker_cuda_home(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=f"# Removed CUDA_HOME for ROCm portability: {line.strip()}",
            rationale="Dockerfile CUDA_HOME forces CUDA toolkit paths; ROCm uses ROCM_PATH.",
        )
    ]


def _rule_docker_cuda_visible_devices(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = re.sub(
        r"\bCUDA_VISIBLE_DEVICES\b",
        "HIP_VISIBLE_DEVICES",
        line,
    )
    if replacement == line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="ROCm reads HIP_VISIBLE_DEVICES (and ROCR_VISIBLE_DEVICES) instead of CUDA_VISIBLE_DEVICES.",
        )
    ]


def _rule_torch_dtype_float16(issue: dict, source_files: dict[str, str], _edits: list[Edit]) -> list[Edit]:
    filename = str(issue.get("file", ""))
    if not _is_py(filename) or filename not in source_files:
        return []
    line_no = int(issue.get("line", 0))
    _, line, _ = _file_lines(source_files, filename, line_no)
    if not line:
        return []
    replacement = re.sub(
        r"\btorch_dtype\s*=\s*torch\.(?:float16|half)\b",
        "torch_dtype=torch.bfloat16",
        line,
    )
    if replacement == line:
        return []
    return [
        Edit(
            file=filename,
            original_block=line,
            replacement_block=replacement,
            rationale="bfloat16 is generally faster and more numerically stable than float16 on MI300X.",
        )
    ]


# ---------------------------------------------------------------------------
# Runtime (post-QA-failure) rules
# ---------------------------------------------------------------------------


def _rule_runtime_cuda_tool_missing(issue: dict, source_files: dict[str, str], edits: list[Edit]) -> list[Edit]:
    """Runtime saw FileNotFoundError for nvidia-smi/nvcc — same fix as static rule."""
    produced: list[Edit] = []
    for filename, content in source_files.items():
        if not _is_py(filename):
            continue
        for idx, line in enumerate(content.splitlines(), start=1):
            if not _NVIDIA_TOOL_LINE_RE.search(line):
                continue
            fake_issue = {"file": filename, "line": idx, "pattern_id": "nvidia_smi_subprocess"}
            produced.extend(_rule_nvidia_smi_subprocess(fake_issue, source_files, edits))
    return produced


_NVIDIA_TOOL_LINE_RE = re.compile(r"['\"](?:nvidia-smi|nvcc)['\"]")


def _rule_runtime_bnb_dependency(issue: dict, source_files: dict[str, str], edits: list[Edit]) -> list[Edit]:
    """Runtime imported bitsandbytes — re-trigger import removal."""
    produced: list[Edit] = []
    for filename in source_files:
        fake_issue = {"file": filename, "pattern_id": "import_bitsandbytes"}
        produced.extend(_rule_import_bitsandbytes(fake_issue, source_files, edits))
    return produced


def _rule_runtime_dispatched_move(issue: dict, source_files: dict[str, str], edits: list[Edit]) -> list[Edit]:
    """Runtime moved an Accelerate-dispatched model — comment those moves."""
    produced: list[Edit] = []
    for filename, content in source_files.items():
        if not _is_py(filename):
            continue
        hf_models = _hf_model_variables(content)
        if not hf_models or "device_map" not in content:
            continue
        for idx, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            indent = line[: len(line) - len(line.lstrip())]
            match = re.match(r"(?P<var>[A-Za-z_][A-Za-z0-9_\.]*)\.(?:cuda|to)\(", stripped)
            if not match:
                continue
            if match.group("var") not in hf_models:
                continue
            produced.append(
                Edit(
                    file=filename,
                    original_block=line,
                    replacement_block=f"{indent}# Removed {stripped}; HF Accelerate dispatch hooks own device placement.",
                    rationale="Manually moving an Accelerate-dispatched model raises 'modules offloaded' at runtime.",
                )
            )
    return produced


# ---------------------------------------------------------------------------
# Cross-cutting post-pass: ensure `device =` exists if any edit uses it
# ---------------------------------------------------------------------------


def _global_post_edits(
    issues: list[dict],
    source_files: dict[str, str],
    edits: list[Edit],
    seen_keys: set[tuple[str, str]],
) -> list[Edit]:
    """Inject a module-level `device = torch.device(...)` when any edit needs it.

    A line uses `device` if a replacement contains `.to(device` or the literal
    device-def string. We inject after the FIRST top-level `import torch` line
    so cross-method/cross-class users can reference it.
    """
    extra: list[Edit] = []
    files_using_device: set[str] = set()
    for edit in edits:
        if ".to(device" in edit.replacement_block or _DEVICE_DEF in edit.replacement_block:
            files_using_device.add(edit.file)

    for filename in files_using_device:
        content = source_files.get(filename, "")
        if not _is_py(filename) or not content:
            continue
        # Already has a module-level `device =` definition somewhere.
        if re.search(r"^device\s*=", content, flags=re.MULTILINE):
            continue
        # Skip if another edit already adds the device def at module scope.
        already_added = any(
            e.file == filename
            and e.replacement_block.startswith(_DEVICE_DEF.split("=", 1)[0].strip())
            for e in edits
        )
        if already_added:
            continue

        anchor_line = _find_last_toplevel_import(content)
        if anchor_line is None:
            continue
        key = (filename, anchor_line)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        extra.append(
            Edit(
                file=filename,
                original_block=anchor_line,
                replacement_block=f"{anchor_line}\n\n{_DEVICE_DEF}",
                rationale="Define a module-level portable torch device so migrated `.to(device)` calls resolve from any function/class.",
            )
        )
    return extra


def _find_last_toplevel_import(content: str) -> str | None:
    """Return the literal text of the last top-level import line in `content`.

    The returned string is suitable as `original_block` for an Edit. We require
    that the line not be inside a try/if/conditional, by checking that it has
    zero indentation and that no later top-level import follows it.
    """
    lines = content.splitlines()
    last_import_idx = -1
    for i, line in enumerate(lines):
        if not line:
            continue
        if line[0] in (" ", "\t"):
            continue
        stripped = line.lstrip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            last_import_idx = i

    if last_import_idx < 0:
        return None

    anchor_line = lines[last_import_idx]
    # Make sure the literal anchor_line is unique enough; if not, fall back to
    # `import torch` (the post-pass caller already filtered for files using
    # torch).
    if content.count(anchor_line) > 1:
        for fallback in ("import torch", "import torch as torch"):
            if content.count(fallback) == 1:
                return fallback
        return None
    return anchor_line


def _hf_model_variables(content: str) -> set[str]:
    variables: set[str] = set()
    for match in re.finditer(
        r"(?m)^\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*AutoModel\w*\.from_pretrained\(",
        content,
    ):
        variables.add(match.group("var"))
    for match in re.finditer(
        r"(?m)^\s*self\.(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*AutoModel\w*\.from_pretrained\(",
        content,
    ):
        variables.add(f"self.{match.group('var')}")
    return variables


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


RULES: dict[str, RuleFn] = {
    "import_bitsandbytes": _rule_import_bitsandbytes,
    "hf_bitsandbytes_quant": _rule_hf_bitsandbytes_quant,
    "hf_device_map_cuda": _rule_device_map_cuda,
    "hardcoded_gpu": _rule_hardcoded_gpu,
    "cuda_home_ref": _rule_cuda_home_ref,
    "cuda_visible_devices": _rule_cuda_visible_devices,
    "nvidia_smi_subprocess": _rule_nvidia_smi_subprocess,
    "pytorch_to_cuda_string": _rule_to_cuda_string,
    "device_string_cuda": _rule_device_string_cuda,
    "pytorch_cuda_method": _rule_pytorch_cuda_method,
    "dep_cuda_only": _rule_dep_cuda_only,
    "dep_torch_cuda_wheel": _rule_dep_torch_cuda_wheel,
    "dep_pinned_version_conflict": _rule_dep_pinned_version_conflict,
    "docker_nvidia_base": _rule_docker_nvidia_base,
    "docker_cuda_home": _rule_docker_cuda_home,
    "docker_cuda_visible_devices": _rule_docker_cuda_visible_devices,
    "torch_dtype_float16": _rule_torch_dtype_float16,

    # Runtime classifications — same outputs, different triggers
    "runtime_cuda_tool_missing": _rule_runtime_cuda_tool_missing,
    "runtime_bitsandbytes_dependency": _rule_runtime_bnb_dependency,
    "runtime_missing_module": _rule_runtime_bnb_dependency,
    "runtime_accelerate_dispatched_model_move": _rule_runtime_dispatched_move,
}
