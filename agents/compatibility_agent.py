from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

from crewai import Agent, Crew, LLM, Task


def _build_llm() -> LLM:
    return LLM(
        model=_normalize_model_name(_get_config("VLLM_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")),
        base_url=_get_config("VLLM_ENDPOINT_URL"),
        api_key=_get_config("VLLM_API_KEY"),
    )


def _get_config(key: str, default: str = "") -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value

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


def _normalize_model_name(model_name: str) -> str:
    if "/" in model_name and model_name.split("/", 1)[0] in {"openai", "hosted_vllm"}:
        return model_name
    return f"hosted_vllm/{model_name}"


compatibility_agent = Agent(
    role="Compatibility Analyst",
    goal="Enrich each detected issue with a severity rationale and a one-line AMD fix hint",
    backstory=(
        "You are a GPU compatibility expert who knows the ROCm ecosystem deeply."
    ),
    llm=_build_llm(),
)


def run_compatibility_agent(issues: list[dict]) -> list[dict]:
    """Enrich scanner issues with compatibility risk and AMD replacement hints."""
    if not issues:
        return []

    prompt = (
        "You are the ROCmForge Compatibility Analyst. Return ONLY JSON with key "
        "'issues'. Each issue must preserve all original fields and add "
        "'compatibility_risk' and 'amd_fix_hint'. Issues JSON:\n"
        f"{json.dumps(issues, ensure_ascii=True)}"
    )
    task = Task(
        description=prompt,
        expected_output="A JSON object with an issues array.",
        agent=compatibility_agent,
    )

    try:
        response = str(Crew(agents=[compatibility_agent], tasks=[task], verbose=False).kickoff())
        parsed = json.loads(_extract_json_object(response))
        enriched = parsed.get("issues", parsed if isinstance(parsed, list) else [])
        if isinstance(enriched, list) and enriched:
            return [_merge_issue(original, item) for original, item in zip(issues, enriched)]
    except Exception:
        pass

    return [_fallback_enrich(issue) for issue in issues]


def _merge_issue(original: dict, enriched: object) -> dict:
    merged = dict(original)
    if isinstance(enriched, dict):
        merged.update(enriched)
    if not merged.get("compatibility_risk") or not merged.get("amd_fix_hint"):
        merged = _fallback_enrich(merged)
    return merged


def _fallback_enrich(issue: dict) -> dict:
    enriched = dict(issue)
    pattern_id = str(issue.get("pattern_id", ""))
    hints = {
        "docker_nvidia_base": "Use a ROCm-capable base image such as rocm/pytorch.",
        "pytorch_cuda_method": "Use torch.device and move tensors/models with .to(device).",
        "dep_cuda_only": "Replace CUDA-only packages with ROCm-compatible alternatives.",
        "import_bitsandbytes": "Use Optimum-AMD, AutoGPTQ, or a ROCm-native quantization path.",
        "readme_cuda_mention": "Document ROCm setup commands alongside any CUDA references.",
        "hardcoded_gpu": "Avoid hardcoded CUDA device setup and detect accelerator availability.",
    }
    enriched.setdefault("compatibility_risk", f"{issue.get('severity', 'medium')} ROCm portability risk")
    enriched.setdefault("amd_fix_hint", hints.get(pattern_id, "Replace CUDA/NVIDIA-specific code with ROCm-compatible logic."))
    return enriched


def _extract_json_object(response: str) -> str:
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        return text[start : end + 1]
    return text
