import os

from crewai import Agent, LLM, Tool

from docs_rag.retriever import retrieve


def _build_llm() -> LLM:
    return LLM(
        model="openai/Qwen/Qwen2.5-1.5B-Instruct",
        base_url=os.environ.get("VLLM_ENDPOINT_URL"),
        api_key=os.environ.get("VLLM_API_KEY"),
    )


def _retrieve_chunks(query: str, k: int = 4) -> str:
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


RAGTool = Tool(
    name="RAGTool",
    description="Retrieve ROCm documentation chunks for a given query.",
    func=_retrieve_chunks,
)

knowledge_agent = Agent(
    role="ROCm Knowledge Base",
    goal="Retrieve AMD documentation and summarise the recommended fix for each issue",
    backstory="You have deep knowledge of ROCm documentation and AMD GPU best practices.",
    llm=_build_llm(),
    tools=[RAGTool],
)
