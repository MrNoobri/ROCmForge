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
) -> str:
    """Build and save the migration report. Returns the markdown string."""

    def _escape_cell(value: object) -> str:
        return str(value).replace("|", r"\|")

    # Issues table
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

    # Generated files list
    if generated_files:
        files_list = "\n".join(f"- `{name}`" for name in generated_files)
    else:
        files_list = "_No new files generated._"

    report = f"""# ROCmForge Migration Report

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

- **Status:** {qa_result.get('status', 'unknown')}
- **Runtime:** {qa_result.get('runtime_sec', 0.0)}s
- **GPU Memory:** {qa_result.get('gpu_memory_gb', 0.0)} GB
- **Logs:** {qa_result.get('logs', '')}

## Notes

{commentary}
"""

    OUTPUTS_DIR.mkdir(exist_ok=True)
    (OUTPUTS_DIR / "migration_report.md").write_text(report, encoding="utf-8")

    return report
