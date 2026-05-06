"""Scoring helpers for AMD readiness calculations."""

from __future__ import annotations

from core.pattern_scanner import Issue


def score(issues: list[Issue], qa_result: dict) -> int:
    """Compute readiness score from issues and QA result."""
    total = 100

    if any(issue.pattern_id == "docker_nvidia_base" for issue in issues):
        total -= 20
    if any(issue.pattern_id == "pytorch_cuda_method" for issue in issues):
        total -= 15
    total -= 15 * sum(1 for issue in issues if issue.pattern_id == "dep_cuda_only")
    if any(issue.pattern_id == "readme_cuda_mention" for issue in issues):
        total -= 10
    if qa_result.get("status") == "failed":
        total -= 20

    return max(total, 0)


def score_before(issues: list[Issue]) -> int:
    return score(issues, {"status": "failed"})


def score_after(issues: list[Issue], qa_result: dict) -> int:
    return score(issues, qa_result)
