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

>>> issues = _scan_text('subprocess.run(["nvidia-smi"])\\n', "main.py")
>>> any(i.pattern_id == "nvidia_smi_subprocess" for i in issues)
True

>>> issues = _scan_text('os.environ["CUDA_VISIBLE_DEVICES"] = "0"\\n', "main.py")
>>> any(i.pattern_id == "cuda_visible_devices" for i in issues)
True

>>> issues = _scan_text('x = x.to("cuda")\\n', "main.py")
>>> any(i.pattern_id == "pytorch_to_cuda_string" for i in issues)
True
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
_REQ_CUDA_ONLY_RE = re.compile(r"^(bitsandbytes|flash-attn|nvidia-)\b", re.IGNORECASE)
_REQ_TORCH_CU_RE = re.compile(r"\+cu\d{2,3}\b", re.IGNORECASE)
# Packages commonly pinned too old for the ROCm sandbox (which ships vllm, newer pydantic, etc.)
_REQ_PINNED_CONFLICT_RE = re.compile(
    r"^(pydantic|fastapi|uvicorn|starlette|transformers|tokenizers|accelerate)==",
    re.IGNORECASE,
)
_NVCC_RE = re.compile(r"\bnvcc\b", re.IGNORECASE)
_CUDA_HOME_RE = re.compile(r"CUDA_HOME")
_CUDA_VISIBLE_RE = re.compile(r"CUDA_VISIBLE_DEVICES")
_README_CUDA_RE = re.compile(r"nvidia-smi|CUDA Toolkit", re.IGNORECASE)
_TORCH_SET_DEVICE_RE = re.compile(r"torch\.cuda\.set_device\(")
_HF_BNB_QUANT_RE = re.compile(r"\bload_in_(?:4bit|8bit)\s*=\s*True\b")
_DEVICE_MAP_CUDA_RE = re.compile(r"\bdevice_map\s*=\s*['\"]cuda['\"]")
_HF_AUTOMODEL_RE = re.compile(r"\bAuto(?:Tokenizer|ModelFor\w*)\b")
_NVIDIA_SMI_SUBPROCESS_RE = re.compile(
    r"subprocess\.(?:run|Popen|check_output|check_call|call)\s*\(\s*\[?\s*['\"](?:nvidia-smi|nvcc)['\"]"
)
_NVIDIA_SMI_BARE_CALL_RE = re.compile(r"['\"](?:nvidia-smi|nvcc)['\"]")
_TO_CUDA_STRING_RE = re.compile(r"\.to\(\s*['\"]cuda(?::\d+)?['\"]\s*[\),]")
_DEVICE_EQ_CUDA_RE = re.compile(
    r"""(?x)
    \b(?:device|DEVICE|self\.device)
    \s*=\s*
    (?:torch\.device\s*\(\s*)?
    ['\"]cuda(?::\d+)?['\"]
    """
)
_TORCH_DTYPE_F16_RE = re.compile(
    r"\btorch_dtype\s*=\s*torch\.(?:float16|half)\b"
)
_TORCH_TENSOR_F16_RE = re.compile(r"\bdtype\s*=\s*torch\.(?:float16|half)\b")
_AUTOCAST_F16_RE = re.compile(r"torch\.(?:cuda\.)?amp\.autocast\b")
_PIN_MEMORY_RE = re.compile(r"\bpin_memory\s*=\s*True\b")
_NCCL_BACKEND_RE = re.compile(r"['\"]nccl['\"]")


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
            if _is_comment_only(line, filename):
                continue
            if regex.search(line):
                add_issue(index, severity, pattern_id, line, description)

    if filename == "Dockerfile":
        scan_regex(
            _DOCKER_NVIDIA_RE,
            "high",
            "docker_nvidia_base",
            "Dockerfile uses an NVIDIA CUDA base image.",
        )
        for index, line in enumerate(lines, start=1):
            if _is_comment_only(line, filename):
                continue
            stripped = line.strip()
            if re.match(r"^ENV\s+CUDA_HOME\b", stripped):
                add_issue(
                    index,
                    "medium",
                    "docker_cuda_home",
                    line,
                    "Dockerfile sets CUDA_HOME; use ROCM_PATH for ROCm builds.",
                )
            elif re.match(r"^ENV\s+CUDA_VISIBLE_DEVICES\b", stripped):
                add_issue(
                    index,
                    "medium",
                    "docker_cuda_visible_devices",
                    line,
                    "Dockerfile sets CUDA_VISIBLE_DEVICES; ROCm uses HIP_VISIBLE_DEVICES.",
                )

    if filename.lower() == "requirements.txt":
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if _REQ_CUDA_ONLY_RE.search(stripped):
                add_issue(
                    index,
                    "high",
                    "dep_cuda_only",
                    line,
                    "Dependency is CUDA-only and may not work on ROCm.",
                )
            elif _REQ_TORCH_CU_RE.search(stripped):
                add_issue(
                    index,
                    "high",
                    "dep_torch_cuda_wheel",
                    line,
                    "PyTorch wheel pinned to a CUDA build (+cuXXX); replace with the ROCm wheel index.",
                )
            elif _REQ_PINNED_CONFLICT_RE.search(stripped):
                add_issue(
                    index,
                    "medium",
                    "dep_pinned_version_conflict",
                    line,
                    "Hard-pinned version (==) may conflict with ROCm sandbox packages; relax to >= bound.",
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
        scan_regex(
            _HF_AUTOMODEL_RE,
            "low",
            "hf_transformers_model",
            "Transformers AutoModel/AutoTokenizer usage may benefit from ROCm vLLM serving.",
        )
        scan_regex(
            _CUDA_VISIBLE_RE,
            "medium",
            "cuda_visible_devices",
            "CUDA_VISIBLE_DEVICES is set; ROCm uses HIP_VISIBLE_DEVICES (or ROCR_VISIBLE_DEVICES).",
        )
        for index, line in enumerate(lines, start=1):
            if _is_comment_only(line, filename):
                continue
            if _NVIDIA_SMI_BARE_CALL_RE.search(line) and _is_likely_subprocess_arg(lines, index - 1):
                add_issue(
                    index,
                    "high",
                    "nvidia_smi_subprocess",
                    line,
                    "Subprocess invokes nvidia-smi/nvcc which is not present on ROCm hosts.",
                )
        scan_regex(
            _TO_CUDA_STRING_RE,
            "medium",
            "pytorch_to_cuda_string",
            'Tensor/model uses .to("cuda") instead of a portable device variable.',
        )
        for index, line in enumerate(lines, start=1):
            if _is_comment_only(line, filename):
                continue
            if "is_available" in line:
                # Already a portable check (e.g. torch.cuda.is_available()).
                continue
            if _DEVICE_EQ_CUDA_RE.search(line):
                add_issue(
                    index,
                    "medium",
                    "device_string_cuda",
                    line,
                    'device variable hardcoded to "cuda"; use torch.cuda.is_available() check.',
                )
        scan_regex(
            _TORCH_DTYPE_F16_RE,
            "low",
            "torch_dtype_float16",
            "torch_dtype=torch.float16; on MI300X, torch.bfloat16 is generally faster and more numerically stable.",
        )
        scan_regex(
            _AUTOCAST_F16_RE,
            "low",
            "torch_amp_autocast",
            "torch.cuda.amp.autocast usage; ROCm supports torch.amp.autocast(device_type=\"cuda\") generically.",
        )
        scan_regex(
            _NCCL_BACKEND_RE,
            "medium",
            "nccl_backend",
            "Distributed backend pinned to NCCL; ROCm uses RCCL (the ProcessGroup name is still \"nccl\" on PyTorch ROCm builds, but verify availability).",
        )

    return issues


def _is_comment_only(line: str, filename: str) -> bool:
    """Return True for lines that are pure comments and shouldn't be flagged.

    For .py and requirements.txt: lines starting with `#`.
    For Dockerfile: lines starting with `#`.
    For README: never skip (markdown can use # for headings).
    """
    if filename.upper().startswith("README"):
        return False
    stripped = line.lstrip()
    if not stripped:
        return True
    return stripped.startswith("#")


def _is_likely_subprocess_arg(lines: list[str], idx: int) -> bool:
    """Look at the surrounding window for a subprocess.* opener.

    `idx` is the 0-based index of the line containing the bare 'nvidia-smi'
    string. We allow up to 3 lines of context above (covers `subprocess.run(\n
    [\n "nvidia-smi"`).
    """
    start = max(0, idx - 3)
    window = "\n".join(lines[start : idx + 1])
    return bool(re.search(r"subprocess\.(?:run|Popen|check_output|check_call|call)\s*\(", window))


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
