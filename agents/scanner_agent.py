import dataclasses
import json
import os

from crewai import Agent, LLM, Tool

from core.pattern_scanner import Issue, scan


def _build_llm() -> LLM:
    return LLM(
        model="openai/Qwen/Qwen2.5-Coder-7B-Instruct",
        base_url=os.environ.get("VLLM_ENDPOINT_URL"),
        api_key=os.environ.get("VLLM_API_KEY"),
    )


def _scan_repository(path: str) -> str:
    issues = scan(path)
    return json.dumps([dataclasses.asdict(issue) for issue in issues])


ScannerTool = Tool(
    name="ScannerTool",
    description="Scan a repository path for CUDA and NVIDIA-specific patterns.",
    func=_scan_repository,
)

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
