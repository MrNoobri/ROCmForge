"""ROCmForge agent orchestrator — single entry point for the Streamlit UI."""

import json
import os
import re
import tempfile
from pathlib import Path

for _proxy_key in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    if os.environ.get(_proxy_key, "").startswith("http://127.0.0.1:9"):
        os.environ.pop(_proxy_key, None)

if os.name == "nt":
    os.environ["LOCALAPPDATA"] = tempfile.gettempdir()

try:
    import appdirs

    appdirs.user_data_dir = lambda appname=None, *_, **__: str(
        Path(tempfile.gettempdir()) / "CrewAI" / str(appname or "ROCmForge")
    )
except ImportError:
    pass

from core.pattern_scanner import Issue
from core.scoring import score_before, score_after
from agents.compatibility_agent import run_compatibility_agent
from agents.knowledge_agent import run_knowledge_agent
from agents.migration_agent import run_migration_agent
from agents.qa_agent import run_qa
from agents.report_agent import run_report_agent
from agents.scanner_agent import run_scanner

_TARGET_FILENAMES = {"dockerfile", "requirements.txt"}
_MAX_QA_RETRIES = 2


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
        A results dict consumed by the Streamlit UI.
    """
    scanner_issues = run_scanner(input_path)
    issues = [_issue_from_dict(issue) for issue in scanner_issues]
    compatibility_issues = run_compatibility_agent(scanner_issues)
    issues_dicts = run_knowledge_agent(compatibility_issues)

    source_files = _read_source_files(input_path)

    attempts: list[dict] = []
    migration_result: dict = {}
    qa_result: dict = {}
    qa_feedback = ""
    runtime_issues: list[dict] = []
    previous_patch = ""
    previous_skipped: list[dict] = []
    issues_json = json.dumps(issues_dicts)
    best_attempt_index = -1  # index into attempts of the most-trustworthy patch
    abort_reason = ""

    for attempt_number in range(1, _MAX_QA_RETRIES + 2):
        migration_result = run_migration_agent(
            issues_json=issues_json,
            source_files=source_files,
            qa_feedback=qa_feedback,
            previous_patch=previous_patch,
            previous_skipped_edits=previous_skipped,
        )

        patched_dir = migration_result.get("patched_dir", "")
        qa_result = run_qa(patched_dir) if patched_dir else {
            "status": "failed",
            "logs": "No patched directory produced by migration agent.",
            "runtime_sec": 0.0,
            "gpu_memory_gb": 0.0,
            "exit_code": -1,
        }

        new_runtime_issues = _runtime_issues_from_qa(qa_result)
        failure_class = _classify_failure(new_runtime_issues)

        attempts.append(
            {
                "attempt": attempt_number,
                "patch": migration_result.get("patch_text", ""),
                "qa_result": qa_result,
                "commentary": migration_result.get("commentary", ""),
                "edits_raw": migration_result.get("edits_raw", []),
                "applied_edits": migration_result.get("applied_edits", []),
                "skipped_edits": migration_result.get("skipped_edits", []),
                "deterministic_edit_count": migration_result.get("deterministic_edit_count", 0),
                "llm_edit_count": migration_result.get("llm_edit_count", 0),
                "llm_rejected_edits": migration_result.get("llm_rejected_edits", []),
                "failure_class": failure_class,
                "runtime_issues": new_runtime_issues,
            }
        )
        best_attempt_index = len(attempts) - 1

        if qa_result.get("status") != "failed":
            break

        # Stop retrying if the failure is not a migration issue.
        if failure_class in ("app_bug", "environment"):
            abort_reason = (
                f"Stopped retrying: failure classified as '{failure_class}'. "
                "ROCmForge migrated the CUDA/ROCm patterns; the remaining error "
                "is pre-existing in the source code or environment and is not a "
                "migration concern."
            )
            break

        # Stop retrying if this attempt regressed (LLM made things worse).
        if attempt_number > 1 and _is_regression(attempts):
            abort_reason = (
                "Stopped retrying: latest attempt introduced new errors that "
                "did not exist in the prior attempt — reverting to the prior "
                "best patch."
            )
            best_attempt_index = len(attempts) - 2
            break

        runtime_issues = _merge_runtime_issues(runtime_issues, new_runtime_issues)
        issues_json = json.dumps(issues_dicts + runtime_issues)
        qa_feedback = json.dumps(
            {
                "runtime_issues": runtime_issues,
                "logs": str(qa_result.get("logs", ""))[-4000:],
            },
            ensure_ascii=True,
        )
        previous_patch = migration_result.get("patch_text", "")
        previous_skipped = migration_result.get("skipped_edits", [])

    # If we reverted, use the best attempt's results for the report.
    if best_attempt_index >= 0 and best_attempt_index < len(attempts) - 1:
        chosen = attempts[best_attempt_index]
        migration_result = {
            "patch_text": chosen.get("patch", ""),
            "generated_files": migration_result.get("generated_files", {}),
            "commentary": chosen.get("commentary", ""),
            "edits_raw": chosen.get("edits_raw", []),
            "patched_dir": migration_result.get("patched_dir", ""),
            "applied_edits": chosen.get("applied_edits", []),
            "skipped_edits": chosen.get("skipped_edits", []),
        }
        qa_result = chosen.get("qa_result", qa_result)

    sb = score_before(issues)
    final_patched_dir = migration_result.get("patched_dir", "")
    after_issue_dicts = run_scanner(final_patched_dir) if final_patched_dir else []
    after_issues = [_issue_from_dict(issue) for issue in after_issue_dicts]

    # If failure is non-migration (app_bug/environment), the migration itself
    # succeeded — score should reflect that, not the runtime crash.
    final_failure_class = attempts[-1].get("failure_class", "unknown") if attempts else "unknown"
    score_qa_result = qa_result
    if qa_result.get("status") == "failed" and final_failure_class in ("app_bug", "environment"):
        score_qa_result = {**qa_result, "status": "migration_ok_app_failed"}
    sa = score_after(after_issues, score_qa_result)

    report_issues = issues_dicts + runtime_issues
    report_markdown = run_report_agent(
        issues=report_issues,
        patch_text=migration_result.get("patch_text", ""),
        generated_files=migration_result.get("generated_files", {}),
        qa_result=qa_result,
        score_before=sb,
        score_after=sa,
        commentary=migration_result.get("commentary", ""),
        failure_class=final_failure_class,
        abort_reason=abort_reason,
    )

    return {
        "issues": issues_dicts,
        "patch_text": migration_result.get("patch_text", ""),
        "generated_files": migration_result.get("generated_files", {}),
        "qa_result": qa_result,
        "score_before": sb,
        "score_after": sa,
        "issues_after": after_issue_dicts,
        "runtime_issues": runtime_issues,
        "failure_class": final_failure_class,
        "abort_reason": abort_reason,
        "report_markdown": report_markdown,
        "attempts": attempts,
        "skipped_edits": migration_result.get("skipped_edits", []),
        "applied_edits": migration_result.get("applied_edits", []),
        "agent_outputs": {
            "scanner": scanner_issues,
            "compatibility": compatibility_issues,
            "knowledge": issues_dicts,
            "runtime": runtime_issues,
        },
    }


def _issue_from_dict(issue: dict) -> Issue:
    return Issue(
        file=str(issue.get("file", "")),
        line=int(issue.get("line", 0)),
        severity=issue.get("severity", "medium"),
        pattern_id=str(issue.get("pattern_id", "")),
        snippet=str(issue.get("snippet", "")),
        description=str(issue.get("description", "")),
    )


# ---------------------------------------------------------------------------
# Runtime log classifier
# ---------------------------------------------------------------------------


def _runtime_issues_from_qa(qa_result: dict) -> list[dict]:
    if qa_result.get("status") != "failed":
        return []

    logs = str(qa_result.get("logs", ""))
    lower_logs = logs.lower()
    issues: list[dict] = []

    # FileNotFoundError for nvidia-smi / nvcc / cuda binaries
    fnf_match = re.search(
        r"FileNotFoundError:\s+\[Errno\s*\d+\]\s*[^:]+:\s*['\"]([^'\"]+)['\"]",
        logs,
    )
    if fnf_match:
        target = fnf_match.group(1)
        if any(tool in target for tool in ("nvidia-smi", "nvcc", "cuda")):
            issues.append(
                _runtime_issue(
                    "runtime_cuda_tool_missing",
                    f"Runtime tried to invoke CUDA-only tool: {target}",
                    target,
                )
            )

    # ModuleNotFoundError / ImportError
    missing_match = re.search(
        r"(?:ModuleNotFoundError|ImportError):\s+No module named ['\"]([^'\"]+)['\"]",
        logs,
    )
    if missing_match:
        module_name = missing_match.group(1)
        issues.append(
            _runtime_issue(
                "runtime_missing_module",
                f"Missing Python module at AMD runtime: {module_name}",
                module_name,
            )
        )
        if module_name == "bitsandbytes":
            issues.append(
                _runtime_issue(
                    "runtime_bitsandbytes_dependency",
                    "Runtime tried to import CUDA-specific bitsandbytes.",
                    module_name,
                )
            )

    if "bitsandbytes" in lower_logs and ("quantization" in lower_logs or "load_in_" in lower_logs):
        issues.append(
            _runtime_issue(
                "runtime_bitsandbytes_quantization",
                "Runtime tried to use bitsandbytes quantization.",
                _last_traceback_line(logs),
            )
        )

    if (
        "accelerate hooks" in lower_logs
        or "you can't move a model that has some modules offloaded" in lower_logs
    ):
        issues.append(
            _runtime_issue(
                "runtime_accelerate_dispatched_model_move",
                "Runtime moved a Hugging Face model managed by Accelerate device_map hooks.",
                _last_traceback_line(logs),
            )
        )

    if "torch not compiled with cuda enabled" in lower_logs or "cuda error" in lower_logs:
        issues.append(
            _runtime_issue(
                "runtime_cuda_call",
                "Runtime still reached CUDA-specific execution.",
                _last_traceback_line(logs),
            )
        )

    if "out of memory" in lower_logs or "hip out of memory" in lower_logs:
        issues.append(
            _runtime_issue(
                "runtime_gpu_memory",
                "Runtime exceeded available GPU memory.",
                _last_traceback_line(logs),
            )
        )

    perm_match = re.search(r"PermissionError:\s+\[Errno\s*\d+\][^\n]*", logs)
    if perm_match:
        issues.append(
            _runtime_issue(
                "runtime_permission_error",
                "Runtime hit a permission error; likely a privileged ROCm device path.",
                perm_match.group(0)[:300],
            )
        )

    # Pre-existing app bugs (not migration issues — surface but do not patch).
    app_bug_signals: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(r"tokenizer does not have a padding token", re.IGNORECASE),
            "runtime_app_bug_pad_token",
            "Tokenizer has no pad_token; set tokenizer.pad_token = tokenizer.eos_token before calling tokenizer with padding.",
        ),
        (
            re.compile(r"FileNotFoundError:\s+\[Errno\s*\d+\][^:]*:\s*['\"]([^'\"]+\.(?:json|yaml|yml|csv|txt|jsonl|parquet|safetensors))['\"]"),
            "runtime_app_bug_missing_data",
            "Runtime is missing a non-CUDA data/config file; this is a pre-existing app dependency, not a migration issue.",
        ),
        (
            re.compile(r"argparse\.ArgumentError|the following arguments are required"),
            "runtime_app_bug_cli",
            "Script requires CLI arguments that were not provided to the AMD sandbox runner.",
        ),
        (
            re.compile(r"KeyError:|AttributeError:.*has no attribute", re.MULTILINE),
            "runtime_app_bug_logic",
            "Pre-existing logic error in the source code (KeyError/AttributeError); not introduced by migration.",
        ),
    ]
    for pattern, pid, description in app_bug_signals:
        match = pattern.search(logs)
        if match:
            issues.append(
                _runtime_issue(
                    pid,
                    description,
                    match.group(0)[:300],
                )
            )

    # Environment/host issues (not migration issues either).
    env_signals: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(
                r"SSH connection error:.*(?:Private key file is encrypted|"
                r"Could not decrypt SSH key|Authentication failed|No authentication methods available)",
                re.IGNORECASE,
            ),
            "runtime_env_ssh_key",
            "Sandbox SSH authentication failed; check AMD_SANDBOX_KEY_PATH and AMD_SANDBOX_KEY_PASSPHRASE.",
        ),
        (
            re.compile(r"OSError:.*Network is unreachable|ConnectionError|HTTPError|requests\.exceptions"),
            "runtime_env_network",
            "Sandbox could not reach the network (model download, dataset fetch, etc.).",
        ),
        (
            re.compile(r"OSError: \[Errno 28\] No space left", re.IGNORECASE),
            "runtime_env_disk_full",
            "Sandbox disk filled (likely model download); not a migration issue.",
        ),
    ]
    for pattern, pid, description in env_signals:
        match = pattern.search(logs)
        if match:
            issues.append(
                _runtime_issue(
                    pid,
                    description,
                    match.group(0)[:300],
                )
            )

    if not issues and "traceback" in lower_logs:
        issues.append(
            _runtime_issue(
                "runtime_traceback",
                "AMD QA produced a traceback that requires migration review.",
                _last_traceback_line(logs),
            )
        )

    return issues


# Pattern IDs that mean "this is not something we should ask the LLM to fix"
NON_MIGRATION_PATTERNS = frozenset(
    {
        "runtime_app_bug_pad_token",
        "runtime_app_bug_missing_data",
        "runtime_app_bug_cli",
        "runtime_app_bug_logic",
        "runtime_env_network",
        "runtime_env_disk_full",
        "runtime_env_ssh_key",
    }
)


def _classify_failure(runtime_issues: list[dict]) -> str:
    """Return one of: 'cuda_relevant', 'app_bug', 'environment', 'unknown'."""
    if not runtime_issues:
        return "unknown"
    pids = {str(i.get("pattern_id", "")) for i in runtime_issues}
    cuda_pids = {
        pid for pid in pids
        if pid.startswith("runtime_") and pid not in NON_MIGRATION_PATTERNS
        and not pid.startswith(("runtime_app_bug_", "runtime_env_"))
    }
    if cuda_pids - {"runtime_traceback"}:
        return "cuda_relevant"
    if any(pid.startswith("runtime_app_bug_") for pid in pids):
        return "app_bug"
    if any(pid.startswith("runtime_env_") for pid in pids):
        return "environment"
    if "runtime_traceback" in pids:
        return "cuda_relevant"  # err on the side of trying once
    return "unknown"


def _runtime_issue(pattern_id: str, description: str, snippet: str) -> dict:
    return {
        "file": "AMD QA runtime",
        "line": 0,
        "severity": "high",
        "pattern_id": pattern_id,
        "snippet": snippet,
        "description": description,
    }


def _last_traceback_line(logs: str) -> str:
    for line in reversed(logs.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped[:500]
    return ""


def _is_regression(attempts: list[dict]) -> bool:
    """Detect when the latest attempt is strictly worse than the prior one.

    A regression is: the latest attempt introduces a runtime issue pattern_id
    that the prior attempt did not have, AND that pattern_id is not in the
    'cuda_relevant' family (i.e. the LLM patched away one CUDA error and
    created a new app-level error instead).
    """
    if len(attempts) < 2:
        return False
    prev = attempts[-2]
    cur = attempts[-1]
    prev_pids = {str(i.get("pattern_id", "")) for i in prev.get("runtime_issues", [])}
    cur_pids = {str(i.get("pattern_id", "")) for i in cur.get("runtime_issues", [])}
    new_pids = cur_pids - prev_pids
    if not new_pids:
        return False
    # If any new pid is an app_bug or environment issue, that's a regression.
    return any(
        pid.startswith("runtime_app_bug_") or pid.startswith("runtime_env_")
        for pid in new_pids
    )


def _merge_runtime_issues(existing: list[dict], new_issues: list[dict]) -> list[dict]:
    merged = list(existing)
    seen = {(issue.get("pattern_id"), issue.get("snippet")) for issue in merged}
    for issue in new_issues:
        key = (issue.get("pattern_id"), issue.get("snippet"))
        if key not in seen:
            merged.append(issue)
            seen.add(key)
    return merged
