"""Knowledge agent — attaches ROCm documentation context to issues.

Performance notes:
    - The deterministic migration registry handles many pattern_ids already
      (see core.migration_rules.RULES). Those issues do not need RAG context
      to be migrated, so we skip retrieval for them and supply a static
      one-line note instead.
    - Issues sharing a pattern_id share the same retrieval context, so we
      cache by pattern_id and only hit the RAG once per unique pattern.
"""

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

try:
    from core.migration_rules import RULES as _DETERMINISTIC_RULES
    _DETERMINISTIC_PATTERN_IDS = frozenset(_DETERMINISTIC_RULES.keys())
except Exception:  # pragma: no cover — defensive
    _DETERMINISTIC_PATTERN_IDS = frozenset()


# Short canned context for patterns the deterministic registry already fixes.
# These avoid a RAG round-trip per issue.
_STATIC_CONTEXT: dict[str, str] = {
    "import_bitsandbytes": "bitsandbytes is CUDA-only. On ROCm use Optimum-AMD or AutoGPTQ; remove the import to unblock execution.",
    "hf_bitsandbytes_quant": "load_in_4bit/load_in_8bit invoke bitsandbytes (CUDA-only). Drop the flag and use Optimum-AMD/AutoGPTQ for quantization on ROCm.",
    "hf_device_map_cuda": 'device_map="cuda" pins HF dispatch to CUDA. Use device_map="auto" so Accelerate selects the ROCm device.',
    "hardcoded_gpu": "torch.cuda.set_device hardcodes a CUDA index. Use torch.device('cuda' if torch.cuda.is_available() else 'cpu') for portability across CUDA/ROCm/CPU.",
    "cuda_home_ref": "CUDA_HOME forces CUDA toolkit paths. ROCm uses ROCM_PATH; remove the override to keep the env portable.",
    "cuda_visible_devices": "ROCm honours HIP_VISIBLE_DEVICES (and ROCR_VISIBLE_DEVICES); CUDA_VISIBLE_DEVICES has no effect on ROCm runtimes.",
    "nvidia_smi_subprocess": "nvidia-smi/nvcc are not present on ROCm hosts. Use rocm-smi (or shutil.which to detect) and tolerate missing-tool failures.",
    "pytorch_to_cuda_string": 'Hardcoded .to("cuda") prevents ROCm/CPU fallback. Use a portable device variable.',
    "device_string_cuda": 'device = "cuda" prevents ROCm/CPU fallback. Use torch.cuda.is_available() to pick the device.',
    "pytorch_cuda_method": "Direct .cuda() calls are not portable. Use .to(device) so the same code targets CUDA, ROCm or CPU.",
    "dep_cuda_only": "CUDA-only PyPI dependency; replace with a ROCm-compatible alternative or remove from requirements.",
    "dep_torch_cuda_wheel": "PyTorch wheel pinned to a +cuXXX build. Replace with the ROCm wheel index: --extra-index-url https://download.pytorch.org/whl/rocm6.1",
    "docker_nvidia_base": "Replace nvidia/cuda base images with a ROCm base such as rocm/pytorch.",
    "torch_dtype_float16": "MI300X handles bfloat16 efficiently and with better numerical stability than float16 for transformer inference.",
    "dep_pinned_version_conflict": "Hard-pinned == versions conflict with the ROCm sandbox's pre-installed libs (vllm requires pydantic>=2.12, transformers>=4.56, etc.). Relax to >= bounds.",
    "docker_cuda_home": "CUDA_HOME in Dockerfile forces CUDA toolkit paths; remove or replace with ROCM_PATH for ROCm images.",
    "docker_cuda_visible_devices": "ROCm reads HIP_VISIBLE_DEVICES (and ROCR_VISIBLE_DEVICES) instead of CUDA_VISIBLE_DEVICES in Dockerfiles.",
}


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
    """Attach ROCm documentation context to each compatibility-enriched issue.

    Optimisations:
        - Issues whose pattern_id is in the deterministic migration registry
          get a fast static one-liner instead of a RAG round-trip.
        - For everything else, retrieval results are cached per pattern_id so
          duplicate-pattern issues share a single query.
    """
    enriched_issues: list[dict] = []
    rag_cache: dict[str, list[dict]] = {}

    for issue in issues:
        enriched = dict(issue)
        pattern_id = str(issue.get("pattern_id", ""))
        query = _build_query(issue)

        if pattern_id in _DETERMINISTIC_PATTERN_IDS or pattern_id in _STATIC_CONTEXT:
            chunks: list[dict] = []
            static_note = _STATIC_CONTEXT.get(
                pattern_id,
                "Handled by ROCmForge deterministic migration rules.",
            )
            enriched["rocm_context"] = static_note
            enriched["rocm_sources"] = []
            enriched["knowledge_query"] = query
            enriched["rocm_source_kind"] = "static"
            enriched_issues.append(enriched)
            continue

        # Cache key — same pattern_id should reuse retrieval.
        cache_key = pattern_id or query
        if cache_key in rag_cache:
            chunks = rag_cache[cache_key]
        else:
            try:
                chunks = retrieve(query, k=3)
            except Exception:
                chunks = []
            rag_cache[cache_key] = chunks

        enriched["knowledge_query"] = query
        enriched["rocm_sources"] = [
            {
                "source": chunk.get("source", "unknown"),
                "heading": chunk.get("heading", ""),
            }
            for chunk in chunks
        ]
        enriched["rocm_context"] = _summarize_chunks(chunks)
        enriched["rocm_source_kind"] = "rag"
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
