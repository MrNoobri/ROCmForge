import os
import tomllib
from pathlib import Path

from crewai import Agent, LLM
from crewai.tools import tool

_HF_CACHE = Path(".cache") / "huggingface"
_HF_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_HF_CACHE))
os.environ.setdefault("HF_HUB_CACHE", str(_HF_CACHE / "hub"))

from docs_rag.retriever import retrieve


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


@tool("RAGTool")
def _retrieve_chunks(query: str, k: int = 4) -> str:
    """Retrieve ROCm documentation chunks for a given query."""
    chunks = retrieve(query, k=k)
    formatted_chunks = []
    for chunk in chunks:
        source = chunk.get("source", "unknown")
        heading = chunk.get("heading", "")
        text = chunk.get("text", "")
        formatted_chunks.append(
            f"SOURCE: {source} | HEADING: {heading}\n{text}\n---"
        )
    return "\n".join(formatted_chunks)


RAGTool = _retrieve_chunks

knowledge_agent = Agent(
    role="ROCm Knowledge Base",
    goal="Retrieve AMD documentation and summarise the recommended fix for each issue",
    backstory="You have deep knowledge of ROCm documentation and AMD GPU best practices.",
    llm=_build_llm(),
    tools=[RAGTool],
)


def run_knowledge_agent(issues: list[dict]) -> list[dict]:
    """Attach ROCm documentation context to each compatibility-enriched issue."""
    enriched_issues = []
    for issue in issues:
        enriched = dict(issue)
        query = _build_query(issue)
        try:
            chunks = retrieve(query, k=3)
        except Exception:
            chunks = []

        enriched["knowledge_query"] = query
        enriched["rocm_sources"] = [
            {
                "source": chunk.get("source", "unknown"),
                "heading": chunk.get("heading", ""),
            }
            for chunk in chunks
        ]
        enriched["rocm_context"] = _summarize_chunks(chunks)
        enriched_issues.append(enriched)
    return enriched_issues


def _build_query(issue: dict) -> str:
    parts = [
        "ROCm migration",
        str(issue.get("pattern_id", "")),
        str(issue.get("description", "")),
        str(issue.get("amd_fix_hint", "")),
    ]
    return " ".join(part for part in parts if part).strip()


def _summarize_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "No matching local ROCm documentation chunk was retrieved."
    summaries = []
    for chunk in chunks:
        heading = chunk.get("heading", "")
        text = " ".join(str(chunk.get("text", "")).split())
        if len(text) > 240:
            text = text[:237].rstrip() + "..."
        summaries.append(f"{heading}: {text}" if heading else text)
    return "\n".join(summaries)
