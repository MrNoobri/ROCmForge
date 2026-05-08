"""ROCmForge pattern scanner.

Doctests:
>>> from core.pattern_scanner import _scan_text
>>> issues = _scan_text("import bitsandbytes\\n", "main.py")
>>> [(i.pattern_id, i.severity) for i in issues]
[('import_bitsandbytes', 'high')]

>>> issues = _scan_text("model.cuda()\\n", "model.py")
>>> issues[0].pattern_id
'pytorch_cuda_method'

>>> issues = _scan_text("FROM nvidia/cuda:12.1.0\\n", "Dockerfile")
>>> issues[0].pattern_id
'docker_nvidia_base'
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Iterable, Literal


Severity = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class Issue:
    file: str
    line: int
    severity: Severity
    pattern_id: str
    snippet: str
    description: str


_DOCKER_NVIDIA_RE = re.compile(r"nvidia/cuda", re.IGNORECASE)
_REQ_CUDA_ONLY_RE = re.compile(r"^(bitsandbytes|flash-attn)\b", re.IGNORECASE)
_NVCC_RE = re.compile(r"\bnvcc\b", re.IGNORECASE)
_CUDA_HOME_RE = re.compile(r"CUDA_HOME")
_README_CUDA_RE = re.compile(r"nvidia-smi|CUDA Toolkit", re.IGNORECASE)
_TORCH_SET_DEVICE_RE = re.compile(r"torch\.cuda\.set_device\(")
_HF_BNB_QUANT_RE = re.compile(r"\bload_in_(?:4bit|8bit)\s*=\s*True\b")
_DEVICE_MAP_CUDA_RE = re.compile(r"\bdevice_map\s*=\s*['\"]cuda['\"]")


def scan(path: str) -> list[Issue]:
    """Scan a file or directory for CUDA/NVIDIA patterns.

    Args:
        path: A file or directory path.

    Returns:
        A list of detected issues.
    """
    files = list(_iter_target_files(path))
    issues: list[Issue] = []
    for file_path in files:
        issues.extend(_scan_file(file_path))
    return issues


def _iter_target_files(path: str) -> Iterable[str]:
    if os.path.isfile(path):
        if _is_target_file(os.path.basename(path)):
            yield path
        return

    for root, _, filenames in os.walk(path):
        for filename in filenames:
            if _is_target_file(filename):
                yield os.path.join(root, filename)


def _is_target_file(filename: str) -> bool:
    lower_name = filename.lower()
    if lower_name.endswith(".py"):
        return True
    if filename == "Dockerfile":
        return True
    if lower_name == "requirements.txt":
        return True
    if filename.upper().startswith("README"):
        return True
    return False


def _scan_file(file_path: str) -> list[Issue]:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()
    except OSError:
        return []

    return _scan_text(content, os.path.basename(file_path), full_path=file_path)


def _scan_text(content: str, filename: str, *, full_path: str | None = None) -> list[Issue]:
    issues: list[Issue] = []
    lines = content.splitlines()
    display_path = full_path or filename

    def add_issue(
        line_number: int,
        severity: Severity,
        pattern_id: str,
        snippet: str,
        description: str,
    ) -> None:
        issues.append(
            Issue(
                file=display_path,
                line=line_number,
                severity=severity,
                pattern_id=pattern_id,
                snippet=snippet.strip(),
                description=description,
            )
        )

    def scan_regex(regex: re.Pattern[str], severity: Severity, pattern_id: str, description: str) -> None:
        for index, line in enumerate(lines, start=1):
            if regex.search(line):
                add_issue(index, severity, pattern_id, line, description)

    if filename == "Dockerfile":
        scan_regex(
            _DOCKER_NVIDIA_RE,
            "high",
            "docker_nvidia_base",
            "Dockerfile uses an NVIDIA CUDA base image.",
        )

    if filename.lower() == "requirements.txt":
        for index, line in enumerate(lines, start=1):
            match = _REQ_CUDA_ONLY_RE.search(line.strip())
            if match:
                add_issue(
                    index,
                    "high",
                    "dep_cuda_only",
                    line,
                    "Dependency is CUDA-only and may not work on ROCm.",
                )

    if filename.upper().startswith("README"):
        scan_regex(
            _README_CUDA_RE,
            "low",
            "readme_cuda_mention",
            "README references CUDA-specific tooling.",
        )

    scan_regex(
        _NVCC_RE,
        "medium",
        "nvcc_ref",
        "Reference to nvcc suggests a CUDA-specific build step.",
    )
    scan_regex(
        _CUDA_HOME_RE,
        "medium",
        "cuda_home_ref",
        "Reference to CUDA_HOME suggests CUDA-specific configuration.",
    )

    if filename.lower().endswith(".py"):
        issues.extend(_scan_python(content, display_path))
        scan_regex(
            _TORCH_SET_DEVICE_RE,
            "medium",
            "hardcoded_gpu",
            "Hardcoded torch.cuda.set_device usage found.",
        )
        scan_regex(
            _HF_BNB_QUANT_RE,
            "high",
            "hf_bitsandbytes_quant",
            "Hugging Face model load uses bitsandbytes quantization.",
        )
        scan_regex(
            _DEVICE_MAP_CUDA_RE,
            "medium",
            "hf_device_map_cuda",
            'Hugging Face device_map is pinned to "cuda".',
        )

    return issues


def _scan_python(content: str, display_path: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "bitsandbytes":
                    issues.append(
                        Issue(
                            file=display_path,
                            line=node.lineno or 1,
                            severity="high",
                            pattern_id="import_bitsandbytes",
                            snippet="import bitsandbytes",
                            description="bitsandbytes import is CUDA-specific.",
                        )
                    )
        if isinstance(node, ast.ImportFrom):
            if node.module == "bitsandbytes":
                issues.append(
                    Issue(
                        file=display_path,
                        line=node.lineno or 1,
                        severity="high",
                        pattern_id="import_bitsandbytes",
                        snippet="from bitsandbytes import ...",
                        description="bitsandbytes import is CUDA-specific.",
                    )
                )

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "cuda":
                issues.append(
                    Issue(
                        file=display_path,
                        line=node.lineno or 1,
                        severity="medium",
                        pattern_id="pytorch_cuda_method",
                        snippet=".cuda()",
                        description="Direct .cuda() call detected; prefer device-agnostic logic.",
                    )
                )

    return issues


def _parse_args(argv: list[str]) -> str:
    if len(argv) != 2:
        raise SystemExit("Usage: python -m core.pattern_scanner <path>")
    return argv[1]


def _main() -> None:
    target_path = _parse_args(sys.argv)
    results = scan(target_path)
    print(json.dumps([asdict(issue) for issue in results], indent=2))


if __name__ == "__main__":
    _main()
