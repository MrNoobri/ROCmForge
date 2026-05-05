# Text Generation Inference (TGI) — Overview

Text Generation Inference (TGI) is a toolkit by Hugging Face for deploying and serving Large Language Models. It supports high-performance text generation for popular open-source LLMs including Llama, Falcon, StarCoder, BLOOM, and T5.

Key features: continuous batching, token streaming via SSE, tensor parallelism across multiple GPUs, Flash Attention and Paged Attention optimizations, and quantization via bitsandbytes and GPT-Q.

## Status Note

As of 2025, TGI is in maintenance mode. Hugging Face recommends using **vLLM** or **SGLang** for new deployments, as these engines adopt the same `transformers`-compatible model architecture approach TGI pioneered. TGI still works and receives bug fixes, but new feature development has moved to vLLM/SGLang.

For AMD GPU deployments specifically, **vLLM on ROCm is the recommended serving stack** (see `02_vllm_rocm.md`). TGI on AMD is documented in `07_tgi_amd.md` for cases where TGI is already in use.

## When to use TGI vs vLLM on AMD

| Scenario | Recommendation |
|---|---|
| New project on AMD MI300X | vLLM on ROCm |
| Existing TGI deployment, migrating to AMD | TGI ROCm Docker image (see `07_tgi_amd.md`) |
| Need OpenAI-compatible API | vLLM (`--api-key` flag built-in) |
| Need TunableOp GEMM kernel tuning on ROCm | TGI (has built-in TunableOp support) |
