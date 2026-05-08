"""Migration agent for generating ROCm-compatible edits."""

from __future__ import annotations

import json
import os
import re
import tempfile
import tomllib
from pathlib import Path

from crewai import Agent, Crew, LLM, Task

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


def run_migration_agent(issues_json: str, source_files: dict[str, str]) -> dict:
    """Run the migration agent and apply edits to a temp workspace."""
    issues = _safe_load_issues(issues_json)
    extra_new_files, extra_commentary = _collect_extras(issues)

    llm = _build_llm()
    source_files_json = json.dumps(source_files, ensure_ascii=True)
    prompt = _build_prompt(issues_json, source_files_json)

    parsed = _request_migration_output(llm, prompt)
    if parsed is None or (not parsed.edits and not parsed.new_files):
        migration = _fallback_migration(issues, source_files)
    else:
        migration = _merge_extras(parsed, extra_new_files, extra_commentary)

    source_dir = _materialize_source_files(source_files)
    patch_result = apply_edits(migration, source_dir)

    return {
        "patch_text": patch_result["patch_text"],
        "generated_files": patch_result["generated_files"],
        "commentary": migration.commentary,
        "edits_raw": [edit.model_dump() for edit in migration.edits],
        "patched_dir": patch_result["patched_dir"],
    }


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


def _build_prompt(issues_json: str, source_files_json: str) -> str:
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        "Issues JSON:\n"
        f"{issues_json}\n\n"
        "Source files JSON (filename -> content):\n"
        f"{source_files_json}\n\n"
        "Return a JSON object with keys: edits (list), new_files (object), commentary (string)."
    )


def _request_migration_output(llm: LLM, prompt: str) -> MigrationOutput | None:
    response = _run_llm(llm, prompt)
    parsed, error = _parse_migration_output(response)
    if parsed is not None:
        return parsed

    retry_prompt = (
        f"{prompt}\n\nYour previous response was not valid JSON. Error: {error}. "
        "Try again, output ONLY the JSON object."
    )
    response = _run_llm(llm, retry_prompt)
    parsed, _ = _parse_migration_output(response)
    return parsed


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
        if pattern_id in {"import_bitsandbytes", "dep_cuda_only"} and "bitsandbytes" in snippet.lower():
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


def _merge_extras(
    migration: MigrationOutput,
    extra_files: dict[str, str],
    extra_commentary: str,
) -> MigrationOutput:
    if not extra_files and not extra_commentary:
        return migration

    new_files = dict(migration.new_files)
    for filename, content in extra_files.items():
        if filename in new_files:
            new_files[filename] = new_files[filename].rstrip() + "\n\n" + content
        else:
            new_files[filename] = content

    commentary = migration.commentary
    if extra_commentary:
        commentary = (commentary + "\n\n" if commentary else "") + extra_commentary

    return MigrationOutput(edits=migration.edits, new_files=new_files, commentary=commentary)


def _fallback_migration(issues: list[dict], source_files: dict[str, str]) -> MigrationOutput:
    edits: list[Edit] = []
    commentary = [
        "Applied deterministic ROCm compatibility edits after the LLM response did not match the strict schema."
    ]

    for filename, content in source_files.items():
        name_lower = Path(filename).name.lower()

        if name_lower.endswith(".py"):
            if "torch.cuda.set_device(0)" in content:
                edits.append(
                    Edit(
                        file=filename,
                        original_block="    torch.cuda.set_device(0)",
                        replacement_block='    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")',
                        rationale="Replace hardcoded CUDA device selection with device-aware logic.",
                    )
                )
            if "model.cuda()" in content:
                edits.append(
                    Edit(
                        file=filename,
                        original_block="model.cuda()",
                        replacement_block="model.to(device)",
                        rationale="Move the model using the selected device instead of direct .cuda().",
                    )
                )
            if "x = x.cuda()" in content:
                edits.append(
                    Edit(
                        file=filename,
                        original_block="x = x.cuda()",
                        replacement_block="x = x.to(device)",
                        rationale="Move tensors using the selected device instead of direct .cuda().",
                    )
                )

        if name_lower == "dockerfile":
            for line in content.splitlines():
                if "nvidia/cuda" in line.lower():
                    edits.append(
                        Edit(
                            file=filename,
                            original_block=line,
                            replacement_block="FROM rocm/pytorch:latest",
                            rationale="Replace NVIDIA CUDA base image with a ROCm PyTorch base image.",
                        )
                    )
                    break

        if name_lower == "requirements.txt":
            for dep in ("bitsandbytes", "flash-attn"):
                for line in content.splitlines():
                    if line.lower().startswith(dep):
                        edits.append(
                            Edit(
                                file=filename,
                                original_block=line,
                                replacement_block=f"# Removed CUDA-only dependency for ROCm review: {line}",
                                rationale=f"Flag CUDA-only dependency {dep} for ROCm replacement.",
                            )
                        )

    extra_files, extra_commentary = _collect_extras(issues)
    if extra_commentary:
        commentary.append(extra_commentary)

    return MigrationOutput(
        edits=edits,
        new_files=extra_files,
        commentary="\n\n".join(commentary),
    )


def _materialize_source_files(source_files: dict[str, str]) -> str:
    temp_root = Path(tempfile.mkdtemp(prefix="rocmforge_source_"))
    for rel_path, content in source_files.items():
        target = temp_root / Path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return str(temp_root)
