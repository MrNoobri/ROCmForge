import dataclasses
import json
import os
import tomllib
from pathlib import Path

from crewai import Agent, LLM
from crewai.tools import tool

from core.pattern_scanner import Issue, scan


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


@tool("ScannerTool")
def _scan_repository(path: str) -> str:
    """Scan a repository path for CUDA and NVIDIA-specific patterns."""
    issues = scan(path)
    return json.dumps([dataclasses.asdict(issue) for issue in issues])


def run_scanner(input_path: str) -> list[dict]:
    """Run the scanner agent stage and return static-analysis issues."""
    issues = scan(input_path)
    return [dataclasses.asdict(issue) for issue in issues]


ScannerTool = _scan_repository

scanner_agent = Agent(
    role="Intake & Scanner",
    goal=(
        "Scan a code repository for CUDA and NVIDIA-specific patterns that will "
        "break on AMD ROCm hardware"
    ),
    backstory="You are a static analysis expert specialising in GPU portability.",
    llm=_build_llm(),
    tools=[ScannerTool],
)
