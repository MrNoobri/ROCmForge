import os

from crewai import Agent, LLM


def _build_llm() -> LLM:
    return LLM(
        model="openai/Qwen/Qwen2.5-1.5B-Instruct",
        base_url=os.environ.get("VLLM_ENDPOINT_URL"),
        api_key=os.environ.get("VLLM_API_KEY"),
    )


compatibility_agent = Agent(
    role="Compatibility Analyst",
    goal="Enrich each detected issue with a severity rationale and a one-line AMD fix hint",
    backstory=(
        "You are a GPU compatibility expert who knows the ROCm ecosystem deeply."
    ),
    llm=_build_llm(),
)
