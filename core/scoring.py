"""Scoring helpers for AMD readiness calculations.

Score philosophy:
    - 100 = clean repo, no CUDA-isms, AMD QA passed.
    - The biggest signal is whether the patched code actually ran on real AMD
      ROCm hardware, because that's what ROCmForge uniquely proves.
    - Static issues are penalties; the AMD QA pass is a strong bonus that
      brings a partially-clean migration up to a respectable score.
    - "migration_ok_app_failed" (we migrated correctly but the source code
      had a pre-existing bug like missing pad_token) gets near-full credit
      because the migration itself succeeded.
"""

from __future__ import annotations

from core.pattern_scanner import Issue


_PENALTIES: dict[str, int] = {
    "docker_nvidia_base": 20,
    "import_bitsandbytes": 20,
    "hf_bitsandbytes_quant": 20,
    "dep_cuda_only": 15,
    "dep_torch_cuda_wheel": 15,
    "dep_pinned_version_conflict": 5,
    "pytorch_cuda_method": 12,
    "nvidia_smi_subprocess": 10,
    "hardcoded_gpu": 8,
    "hf_device_map_cuda": 8,
    "cuda_home_ref": 8,
    "docker_cuda_home": 6,
    "cuda_visible_devices": 6,
    "docker_cuda_visible_devices": 5,
    "pytorch_to_cuda_string": 6,
    "device_string_cuda": 6,
    "nvcc_ref": 8,
    "readme_cuda_mention": 5,
    "nccl_backend": 4,
    "torch_dtype_float16": 2,
    "torch_amp_autocast": 2,
}

_MULTI_COUNT_PATTERNS = {"dep_cuda_only", "dep_torch_cuda_wheel"}

# Bonuses applied based on how well the patched code ran.
_QA_PASS_BONUS = 35  # Real ROCm execution succeeded.
_QA_APP_BUG_BONUS = 25  # Migration succeeded; pre-existing app bug remains.
_QA_FAILED_PENALTY = 10  # Reduced from 20 — the issue penalties already reflect quality.


def _static_penalty_total(issues: list[Issue]) -> int:
    """Sum penalties for unique pattern_ids (multi-count families are counted per-occurrence).

    Penalties are also softened with diminishing returns so a deeply CUDA-coupled
    repo doesn't crater to 0 — that hides the actual improvement after migration.
    """
    total = 0
    seen: set[str] = set()
    for issue in issues:
        pid = issue.pattern_id
        penalty = _PENALTIES.get(pid)
        if penalty is None:
            continue
        if pid in _MULTI_COUNT_PATTERNS:
            total += penalty
            continue
        if pid in seen:
            continue
        seen.add(pid)
        total += penalty
    return total


def _diminishing(raw_penalty: int, ceiling: int = 70) -> int:
    """Apply a soft cap so penalties saturate near a ceiling instead of clamping at 0.

    Maps raw penalty x to ceiling * (1 - exp(-x / ceiling)). For x=20 → ~17,
    x=50 → ~35, x=150 → ~62. Keeps the Before score meaningfully above 0 even
    on heavily CUDA-coupled repos so the After delta is visible.
    """
    import math
    return int(round(ceiling * (1 - math.exp(-raw_penalty / ceiling))))


def score(issues: list[Issue], qa_result: dict) -> int:
    """Compute readiness score from issues and QA result."""
    raw = _static_penalty_total(issues)
    total = 100 - _diminishing(raw)

    status = qa_result.get("status")
    if status == "failed":
        total -= _QA_FAILED_PENALTY
    elif status == "migration_ok_app_failed":
        total += _QA_APP_BUG_BONUS
    elif status in ("passed", "success", "ok"):
        total += _QA_PASS_BONUS
    elif status is not None and status != "unknown":
        total += _QA_PASS_BONUS

    return max(min(total, 100), 0)


def score_before(issues: list[Issue]) -> int:
    """Score before migration: portability of the repo as-is, no QA bonus/penalty.

    This is a static measure — how AMD-portable does this codebase look right
    now? We do NOT apply the QA-failed penalty because Before is hypothetical
    (the repo never ran on AMD pre-migration).
    """
    raw = _static_penalty_total(issues)
    return max(0, 100 - _diminishing(raw))


def score_after(issues: list[Issue], qa_result: dict) -> int:
    return score(issues, qa_result)
