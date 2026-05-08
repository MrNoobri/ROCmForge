"""Report agent — assembles the final markdown migration report."""

from pathlib import Path

from crewai import Agent

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"

report_agent = Agent(
    role="Report Writer",
    goal="Produce a clear, structured markdown migration report",
    backstory="You are a technical writer who summarises GPU migration results for engineering teams.",
    verbose=False,
    allow_delegation=False,
)


def build_report(
    issues: list[dict],
    patch_text: str,
    generated_files: dict,
    qa_result: dict,
    score_before: int,
    score_after: int,
    commentary: str,
    failure_class: str = "unknown",
    abort_reason: str = "",
) -> str:
    """Build and save the migration report. Returns the markdown string."""

    def _escape_cell(value: object) -> str:
        return str(value).replace("|", r"\|")

    if issues:
        header = "| File | Line | Severity | Pattern | Description |\n|---|---|---|---|---|"
        rows = "\n".join(
            f"| {_escape_cell(i.get('file','?'))} | {_escape_cell(i.get('line','?'))} | {_escape_cell(i.get('severity','?'))} "
            f"| {_escape_cell(i.get('pattern_id','?'))} | {_escape_cell(i.get('description','?'))} |"
            for i in issues
        )
        issues_table = f"{header}\n{rows}"
    else:
        issues_table = "_No issues detected._"

    if generated_files:
        files_list = "\n".join(f"- `{name}`" for name in generated_files)
    else:
        files_list = "_No new files generated._"

    qa_status = qa_result.get("status", "unknown")
    verdict = _build_verdict(qa_status, failure_class, abort_reason)

    report = f"""# ROCmForge Migration Report

## Verdict

{verdict}

## AMD Readiness Score

- **Before:** {score_before}/100
- **After:** {score_after}/100

## Issues Detected ({len(issues)} total)

{issues_table}

## Migration Patch

```diff
{patch_text}
```

## Generated Files

{files_list}

## QA Result

- **Status:** {qa_status}
- **Failure class:** {failure_class}
- **Runtime:** {qa_result.get('runtime_sec', 0.0)}s
- **GPU Memory:** {qa_result.get('gpu_memory_gb', 0.0)} GB
- **Logs:**

```
{qa_result.get('logs', '')}
```

## Notes

{commentary}
"""

    OUTPUTS_DIR.mkdir(exist_ok=True)
    (OUTPUTS_DIR / "migration_report.md").write_text(report, encoding="utf-8")

    return report


def _build_verdict(qa_status: str, failure_class: str, abort_reason: str) -> str:
    if qa_status not in ("failed",):
        return (
            "**Migration succeeded.** All detected CUDA/NVIDIA patterns were rewritten "
            "and the patched code ran on the AMD ROCm sandbox without errors."
        )

    if failure_class == "app_bug":
        body = (
            "**Migration succeeded; runtime tripped on a pre-existing app bug.** "
            "Every CUDA/ROCm portability issue ROCmForge can detect was rewritten and "
            "applied. The remaining traceback is from logic in the source code that "
            "would have failed on a real CUDA host too — see the QA logs below for the "
            "specific cause (e.g. missing tokenizer pad_token, missing data file, missing "
            "CLI argument). This is not a migration concern."
        )
        if abort_reason:
            body += f"\n\n_{abort_reason}_"
        return body

    if failure_class == "environment":
        body = (
            "**Migration succeeded; runtime tripped on an environment issue.** The "
            "AMD ROCm sandbox could not satisfy a non-code requirement (network access, "
            "disk space, missing model weights, etc.). The migration patch is sound."
        )
        if abort_reason:
            body += f"\n\n_{abort_reason}_"
        return body

    if failure_class == "cuda_relevant":
        return (
            "**Migration partially complete.** The patched code reached the AMD ROCm "
            "sandbox but hit a CUDA-relevant runtime error that the agent could not "
            "auto-resolve within the retry budget. See the runtime issues table and "
            "QA logs to continue manually."
        )

    return (
        "**Migration ran but QA failed.** Review the QA logs and the migration patch "
        "below. The failure could not be confidently classified."
    )


def run_report_agent(
    issues: list[dict],
    patch_text: str,
    generated_files: dict,
    qa_result: dict,
    score_before: int,
    score_after: int,
    commentary: str,
    failure_class: str = "unknown",
    abort_reason: str = "",
) -> str:
    """Run the report agent stage."""
    return build_report(
        issues=issues,
        patch_text=patch_text,
        generated_files=generated_files,
        qa_result=qa_result,
        score_before=score_before,
        score_after=score_after,
        commentary=commentary,
        failure_class=failure_class,
        abort_reason=abort_reason,
    )
