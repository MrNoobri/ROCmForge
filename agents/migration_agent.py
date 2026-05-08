"""Migration agent for generating ROCm-compatible edits.

Architecture:
    1. Deterministic rule registry (core.migration_rules) handles every issue
       it knows how to fix. This is the *primary* fix path.
    2. The LLM is invoked only on issues the registry could not handle, with a
       structured checklist prompt and (on retry) the previous patch + the
       skipped-edit feedback from patch_utils.
    3. Final edits = deterministic edits + LLM edits, merged with the LLM
       losing on conflicts (the registry is canonical).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import tomllib
from pathlib import Path

from crewai import Agent, Crew, LLM, Task

from core.migration_rules import apply_rules
from core.patch_utils import Edit, MigrationOutput, apply_edits


MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"

_KNOWN_PREFIXES = (
    "openai/",
    "anthropic/",
    "claude/",
    "azure/",
    "azure_openai/",
    "google/",
    "gemini/",
    "bedrock/",
    "aws/",
    "openrouter/",
    "deepseek/",
    "ollama/",
    "ollama_chat/",
    "hosted_vllm/",
    "cerebras/",
    "dashscope/",
)

_SYSTEM_PROMPT = (
    "You are a migration engineer. Output ONLY a JSON object with keys "
    "edits, new_files, commentary. Do not include markdown or code fences."
)


def run_migration_agent(
    issues_json: str,
    source_files: dict[str, str],
    qa_feedback: str = "",
    previous_patch: str = "",
    previous_skipped_edits: list[dict] | None = None,
) -> dict:
    """Run the migration agent and apply edits to a temp workspace."""
    issues = _safe_load_issues(issues_json)
    extra_new_files, extra_commentary = _collect_extras(issues)

    # 1. Deterministic rules first.
    deterministic_edits, handled_issues = apply_rules(issues, source_files)
    handled_pattern_ids = {str(i.get("pattern_id", "")) for i in handled_issues}
    unhandled = [i for i in issues if str(i.get("pattern_id", "")) not in handled_pattern_ids]

    # 2. LLM on the residual (skip if everything is already handled and there
    # is no QA feedback to react to).
    llm_edits: list[Edit] = []
    llm_new_files: dict[str, str] = {}
    llm_commentary = ""
    if unhandled or qa_feedback:
        llm_output = _ask_llm(
            unhandled_issues=unhandled,
            source_files=source_files,
            qa_feedback=qa_feedback,
            previous_patch=previous_patch,
            previous_skipped_edits=previous_skipped_edits or [],
            handled_pattern_ids=sorted(handled_pattern_ids),
        )
        if llm_output is not None:
            llm_edits = list(llm_output.edits)
            llm_new_files = dict(llm_output.new_files)
            llm_commentary = llm_output.commentary

    # 3. Validate LLM edits — reject anything that looks like a hallucinated
    # rewrite of working code. The LLM should only touch lines whose original
    # text contains a CUDA/ROCm signal, or lines tied to a known issue.
    validated_llm_edits, rejected_llm_edits = _validate_llm_edits(
        llm_edits, issues, source_files
    )

    # 4. Merge — registry wins on conflicts.
    merged_edits = list(deterministic_edits)
    seen_keys = {(e.file, e.original_block) for e in merged_edits}
    for edit in validated_llm_edits:
        key = (edit.file, edit.original_block)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged_edits.append(edit)

    new_files = dict(extra_new_files)
    for filename, content in llm_new_files.items():
        new_files.setdefault(filename, content)

    commentary_parts: list[str] = []
    if extra_commentary:
        commentary_parts.append(extra_commentary)
    if deterministic_edits:
        commentary_parts.append(
            f"Deterministic registry produced {len(deterministic_edits)} edit(s) covering "
            f"{len(handled_pattern_ids)} pattern(s); LLM handled {len(unhandled)} residual issue(s)."
        )
    if llm_commentary:
        commentary_parts.append(llm_commentary)
    commentary = "\n\n".join(p for p in commentary_parts if p)

    migration = MigrationOutput(
        edits=merged_edits,
        new_files=new_files,
        commentary=commentary,
    )

    source_dir = _materialize_source_files(source_files)
    patch_result = apply_edits(migration, source_dir)

    return {
        "patch_text": patch_result["patch_text"],
        "generated_files": patch_result["generated_files"],
        "commentary": migration.commentary,
        "edits_raw": [edit.model_dump() for edit in migration.edits],
        "patched_dir": patch_result["patched_dir"],
        "applied_edits": patch_result.get("applied_edits", []),
        "skipped_edits": patch_result.get("skipped_edits", []),
        "deterministic_edit_count": len(deterministic_edits),
        "llm_edit_count": len(validated_llm_edits),
        "llm_rejected_edits": rejected_llm_edits,
    }


# ---------------------------------------------------------------------------
# LLM edit validation
# ---------------------------------------------------------------------------

# Tokens that indicate a line is plausibly CUDA/ROCm-related and therefore
# fair game for the LLM to rewrite.
_CUDA_SIGNAL_TOKENS = (
    "cuda",
    "cudnn",
    "nccl",
    "rccl",
    "nvidia",
    "nvcc",
    "nvtx",
    "bitsandbytes",
    "bnb",
    "load_in_4bit",
    "load_in_8bit",
    "device_map",
    "torch.device",
    "set_device",
    "is_available",
    "to(device",
    "torch_dtype",
    "torch.float16",
    "torch.half",
    "torch.bfloat16",
    "autocast",
    "rocm",
    "hip",
    "amp",
    "gpu",
    "flash_attn",
    "flash-attn",
    "from_pretrained",
    "AutoModel",
    "AutoTokenizer",
    "pin_memory",
)


def _validate_llm_edits(
    llm_edits: list[Edit],
    issues: list[dict],
    source_files: dict[str, str],
) -> tuple[list[Edit], list[dict]]:
    """Reject LLM edits that don't touch CUDA-relevant lines.

    Without this guard the LLM tends to "improve" working code (e.g. rewriting
    `padding=True` to `padding='longest'` or `return_tensors="pt"` to
    `return_tensors=torch.Tensor`) under the banner of "ROCm compatibility".
    Only edits whose original_block overlaps a known issue line, a runtime
    traceback line, or contains an explicit CUDA/ROCm signal are kept.
    """
    issue_lines_by_file = _issue_lines_by_file(issues, source_files)
    accepted: list[Edit] = []
    rejected: list[dict] = []

    for edit in llm_edits:
        if not edit.original_block.strip():
            rejected.append(
                {
                    "edit": edit.model_dump(),
                    "reason": "empty_original_block",
                }
            )
            continue

        if _has_cuda_signal(edit.original_block) or _has_cuda_signal(edit.replacement_block):
            accepted.append(edit)
            continue

        # Replacement that ONLY adds a comment / removes code referenced by an
        # issue is acceptable; e.g. "# remove this" replacing a CUDA line.
        if _is_pure_comment_or_removal(edit.replacement_block) and _has_cuda_signal(edit.original_block):
            accepted.append(edit)
            continue

        # Allow if the edit overlaps a known issue line in the same file.
        file_issue_lines = issue_lines_by_file.get(edit.file, set())
        if _overlaps_known_lines(edit.original_block, edit.file, file_issue_lines, source_files):
            accepted.append(edit)
            continue

        rejected.append(
            {
                "edit": edit.model_dump(),
                "reason": "no_cuda_signal_and_no_issue_overlap",
            }
        )

    return accepted, rejected


def _has_cuda_signal(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(token.lower() in lower for token in _CUDA_SIGNAL_TOKENS)


def _is_pure_comment_or_removal(text: str) -> bool:
    if not text.strip():
        return True
    return all(line.lstrip().startswith("#") or not line.strip() for line in text.splitlines())


def _issue_lines_by_file(
    issues: list[dict],
    source_files: dict[str, str],
) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for issue in issues:
        raw_file = str(issue.get("file", ""))
        line = int(issue.get("line", 0) or 0)
        if line <= 0:
            continue
        # Resolve to a source_files key (same logic as migration_rules).
        match = _resolve_to_source_key(raw_file, source_files)
        if match is None:
            continue
        out.setdefault(match, set()).add(line)
    return out


def _resolve_to_source_key(raw: str, source_files: dict[str, str]) -> str | None:
    if not raw:
        return None
    if raw in source_files:
        return raw
    posix = raw.replace("\\", "/")
    if posix in source_files:
        return posix
    for key in source_files:
        if posix.endswith("/" + key) or posix.endswith(key):
            return key
    base = posix.rsplit("/", 1)[-1]
    if base in source_files:
        return base
    return None


def _overlaps_known_lines(
    original_block: str,
    filename: str,
    known_lines: set[int],
    source_files: dict[str, str],
) -> bool:
    if not known_lines:
        return False
    content = source_files.get(filename, "")
    if not content:
        return False

    block_lines = [ln.strip() for ln in original_block.splitlines() if ln.strip()]
    if not block_lines:
        return False

    # For each non-blank line of original_block, find its line number in the
    # source. If any of those line numbers is in known_lines, the block
    # overlaps a known issue.
    source_lines = content.splitlines()
    for block_line in block_lines:
        for idx, source_line in enumerate(source_lines, start=1):
            if block_line in source_line and idx in known_lines:
                return True
    return False


# ---------------------------------------------------------------------------
# LLM plumbing
# ---------------------------------------------------------------------------


def _ask_llm(
    unhandled_issues: list[dict],
    source_files: dict[str, str],
    qa_feedback: str,
    previous_patch: str,
    previous_skipped_edits: list[dict],
    handled_pattern_ids: list[str],
) -> MigrationOutput | None:
    try:
        llm = _build_llm()
    except RuntimeError:
        return None

    prompt = _build_prompt(
        unhandled_issues=unhandled_issues,
        source_files=source_files,
        qa_feedback=qa_feedback,
        previous_patch=previous_patch,
        previous_skipped_edits=previous_skipped_edits,
        handled_pattern_ids=handled_pattern_ids,
    )
    response = _run_llm(llm, prompt)
    parsed, error = _parse_migration_output(response)
    if parsed is not None:
        return parsed

    retry = (
        f"{prompt}\n\nYour previous response was not valid JSON ({error}). "
        "Output ONLY the JSON object, no markdown."
    )
    response = _run_llm(llm, retry)
    parsed, _ = _parse_migration_output(response)
    return parsed


def _build_llm() -> LLM:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    endpoint = _get_config("VLLM_ENDPOINT_URL")
    api_key = _get_config("VLLM_API_KEY")
    if not endpoint or not api_key:
        raise RuntimeError("VLLM_ENDPOINT_URL and VLLM_API_KEY must be set.")
    model_name = _normalize_model_name(_get_config("VLLM_MODEL", MODEL_NAME))
    return LLM(model=model_name, base_url=endpoint, api_key=api_key)


def _get_config(key: str, default: str = "") -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value

    try:
        import streamlit as st

        value = str(st.secrets.get(key, "")).strip()
        if value:
            return value
    except Exception:
        pass

    secrets_path = Path(".streamlit") / "secrets.toml"
    if secrets_path.exists():
        try:
            data = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
            value = str(data.get(key, "")).strip()
            if value:
                return value
        except Exception:
            pass

    return default


def _build_agent(llm: LLM) -> Agent:
    return Agent(
        role="Migration Engineer",
        goal="Produce structured JSON edits to migrate CUDA code to AMD ROCm",
        backstory=(
            "You are an expert in porting PyTorch code from CUDA to ROCm. "
            "You always output valid JSON matching the MigrationOutput schema."
        ),
        llm=llm,
        verbose=False,
    )


def _normalize_model_name(model_name: str) -> str:
    for prefix in _KNOWN_PREFIXES:
        if model_name.startswith(prefix):
            return model_name
    provider = os.environ.get("VLLM_PROVIDER", "hosted_vllm").strip() or "hosted_vllm"
    return f"{provider}/{model_name}"


def _build_prompt(
    unhandled_issues: list[dict],
    source_files: dict[str, str],
    qa_feedback: str,
    previous_patch: str,
    previous_skipped_edits: list[dict],
    handled_pattern_ids: list[str],
) -> str:
    sections: list[str] = [_SYSTEM_PROMPT, ""]

    if handled_pattern_ids:
        sections.append(
            "DETERMINISTIC RULES already produced edits for these patterns "
            f"(do not re-emit them): {', '.join(handled_pattern_ids)}."
        )
        sections.append("")

    if unhandled_issues:
        sections.append(
            "RESIDUAL ISSUES — produce one edit (or new_files entry) per item, "
            "and acknowledge each id in commentary:"
        )
        sections.append(_render_issue_checklist(unhandled_issues))
        sections.append("")
    else:
        sections.append(
            "There are no residual static issues — focus on the QA runtime feedback below."
        )
        sections.append("")

    relevant_sources = _select_relevant_sources(
        unhandled_issues=unhandled_issues,
        source_files=source_files,
        qa_feedback=qa_feedback,
        previous_skipped_edits=previous_skipped_edits,
    )
    if relevant_sources:
        sections.append(
            "Source files JSON (filename -> content) — ONLY files that have "
            "a residual issue or were named in QA feedback are included:"
        )
        sections.append(json.dumps(relevant_sources, ensure_ascii=True))
        sections.append("")
    else:
        sections.append(
            "No source files require LLM editing — every issue is either "
            "handled deterministically or the QA feedback can be addressed "
            "without further code changes."
        )
        sections.append("")

    if previous_patch:
        sections.append(
            "PREVIOUS PATCH (already applied; do not re-emit identical edits, "
            "produce only deltas that fix the runtime failure):"
        )
        sections.append(previous_patch[:6000])
        sections.append("")

    if previous_skipped_edits:
        sections.append(
            "PREVIOUS PATCH SKIPPED EDITS — these edits failed to apply. "
            "Either reformulate them (match exact text in the source) or skip if obsolete:"
        )
        sections.append(json.dumps(previous_skipped_edits, ensure_ascii=True)[:4000])
        sections.append("")

    if qa_feedback:
        sections.append(
            "QA RUNTIME FEEDBACK — treat as authoritative evidence. Produce edits "
            "that fix the root cause, not one-line workarounds:"
        )
        sections.append(qa_feedback[:6000])
        sections.append("")

    sections.append(
        "STRICT RULES — violations will be rejected:\n"
        "1. Edit ONLY lines that contain a CUDA/NVIDIA/ROCm signal "
        "(.cuda(), torch.cuda.*, bitsandbytes, device_map, CUDA_*, nvidia-smi, "
        "torch_dtype=torch.float16, etc.) OR lines explicitly listed as residual "
        "issues above.\n"
        "2. DO NOT edit lines that work fine (e.g. padding=True, "
        "return_tensors=\"pt\", model.eval(), unrelated config). If a runtime "
        "error is from a pre-existing app bug (missing pad_token, missing data "
        "file, bad CLI args), DO NOT try to fix it — note it in commentary "
        "instead.\n"
        "3. original_block MUST appear verbatim in the source file.\n"
        "4. Prefer minimal, surgical edits over rewrites.\n\n"
        "Return JSON: {\"edits\": [{\"file\":..., \"original_block\":..., "
        "\"replacement_block\":..., \"rationale\":...}], "
        "\"new_files\": {filename: content}, \"commentary\": \"...\"}."
    )
    return "\n".join(sections)


_PER_FILE_SOURCE_CAP = 8000  # characters; keeps the prompt bounded


def _select_relevant_sources(
    unhandled_issues: list[dict],
    source_files: dict[str, str],
    qa_feedback: str,
    previous_skipped_edits: list[dict],
) -> dict[str, str]:
    """Return only the source files the LLM needs to see.

    Includes:
        - Files that own at least one residual issue.
        - Files explicitly named in the QA feedback (e.g. traceback paths).
        - Files referenced by skipped edits from the previous attempt.
    Each file's content is capped at _PER_FILE_SOURCE_CAP characters to keep
    prompts bounded for big repos.
    """
    relevant_keys: set[str] = set()

    for issue in unhandled_issues:
        raw = str(issue.get("file", ""))
        key = _resolve_to_source_key(raw, source_files)
        if key is not None:
            relevant_keys.add(key)

    if qa_feedback:
        # Crude but effective: any source_files key whose name appears in the
        # feedback string is included.
        for key in source_files:
            base = key.rsplit("/", 1)[-1]
            if base and base in qa_feedback:
                relevant_keys.add(key)

    for sk in previous_skipped_edits:
        raw = str(sk.get("file", ""))
        key = _resolve_to_source_key(raw, source_files)
        if key is not None:
            relevant_keys.add(key)

    if not relevant_keys:
        return {}

    out: dict[str, str] = {}
    for key in sorted(relevant_keys):
        content = source_files.get(key, "")
        if len(content) > _PER_FILE_SOURCE_CAP:
            content = content[:_PER_FILE_SOURCE_CAP] + "\n# ... (truncated by ROCmForge)"
        out[key] = content
    return out


def _render_issue_checklist(issues: list[dict]) -> str:
    lines: list[str] = []
    for issue in issues:
        lines.append(
            f"- [{issue.get('pattern_id', '?')}] {issue.get('file', '?')}:"
            f"{issue.get('line', 0)} | {issue.get('description', '')} | "
            f"snippet: {str(issue.get('snippet', ''))[:160]}"
        )
        if issue.get("amd_fix_hint"):
            lines.append(f"    fix hint: {issue['amd_fix_hint']}")
        if issue.get("rocm_context"):
            ctx = str(issue["rocm_context"]).replace("\n", " ")
            lines.append(f"    rocm: {ctx[:200]}")
    return "\n".join(lines)


def _run_llm(llm: LLM, prompt: str) -> str:
    agent = _build_agent(llm)
    task = Task(
        description=prompt,
        expected_output="Valid JSON object matching the MigrationOutput schema.",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task])
    result = crew.kickoff()
    return str(result).strip()


def _parse_migration_output(response: str) -> tuple[MigrationOutput | None, str | None]:
    response = _extract_json_object(response)
    try:
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        return None, str(exc)

    try:
        return MigrationOutput.model_validate(data), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _extract_json_object(response: str) -> str:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _safe_load_issues(issues_json: str) -> list[dict]:
    try:
        data = json.loads(issues_json)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _collect_extras(issues: list[dict]) -> tuple[dict[str, str], str]:
    extra_files: dict[str, str] = {}
    extra_commentary = ""

    auto_model_text = ""
    for issue in issues:
        text = f"{issue.get('snippet', '')} {issue.get('description', '')}"
        if "AutoModelFor" in text or "AutoTokenizer" in text:
            auto_model_text = text
            break

    if auto_model_text:
        model_name = _extract_model_name(auto_model_text) or "<your-model>"
        extra_files["rocm_setup.md"] = (
            "## ROCm Optimization Note: vLLM Serving\n\n"
            "vLLM on ROCm can deliver 3-5x higher throughput on MI300X for "
            "transformer inference. Starter command:\n\n"
            f"python -m vllm.entrypoints.openai.api_server --model {model_name} --port 8000\n"
        )

    for issue in issues:
        pattern_id = issue.get("pattern_id", "")
        snippet = issue.get("snippet", "")
        if pattern_id in {"import_bitsandbytes", "dep_cuda_only"} and "bitsandbytes" in str(snippet).lower():
            extra_commentary = (
                "AMD replacement: use Hugging Face Optimum-AMD (pip install optimum[amd]) "
                "or AutoGPTQ - both have native ROCm/Triton support and do not require "
                "building from source."
            )
            break

    return extra_files, extra_commentary


def _extract_model_name(text: str) -> str | None:
    match = re.search(r"from_pretrained\(\s*['\"]([^'\"]+)['\"]", text)
    if match:
        return match.group(1)
    return None


def _materialize_source_files(source_files: dict[str, str]) -> str:
    temp_root = Path(tempfile.mkdtemp(prefix="rocmforge_source_"))
    for rel_path, content in source_files.items():
        target = temp_root / Path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return str(temp_root)
