# Flash Attention on ROCm — Migration Guide

## Why `pip install flash-attn` Fails on AMD

The standard `flash-attn` package (from Tri Dao's repo) compiles CUDA PTX kernels using `nvcc` at install time. On an AMD system, `nvcc` is absent and the CUDA include headers don't exist — the pip install crashes during compilation.

**Remove `flash-attn` from your `requirements.txt`.** You have two replacement paths depending on your use case.

## Option A: `torch.nn.functional.scaled_dot_product_attention` (Recommended)

PyTorch 2.0+ includes a native `scaled_dot_product_attention` (SDPA) that automatically dispatches to an optimal ROCm kernel (memory-efficient attention via MIOpen or a Triton kernel) without any extra installation.

Replace explicit flash-attn calls:

```python
# BEFORE (CUDA flash-attn)
from flash_attn import flash_attn_func
out = flash_attn_func(q, k, v, causal=True)

# AFTER (PyTorch SDPA — works on both CUDA and ROCm)
import torch.nn.functional as F
out = F.scaled_dot_product_attention(q, k, v, is_causal=True)
```

For Hugging Face Transformers models, enable it via `attn_implementation`:

```python
from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-2-7b-hf",
    torch_dtype=torch.float16,
    attn_implementation="sdpa",  # uses SDPA, works on ROCm
)
```

**No requirements.txt change needed beyond removing `flash-attn`.**

## Option B: ROCm/flash-attention CK Fork

For cases where you specifically need the `flash_attn` package (e.g., you're running TGI or a library that imports `flash_attn` directly), use AMD's Composable Kernel fork:

```bash
git clone https://github.com/ROCm/flash-attention.git
cd flash-attention
git checkout 3cea2fb
git submodule update --init

# Set your GPU arch
GPU_ARCHS="gfx942" python3 setup.py install   # MI300X
# or GPU_ARCHS="gfx90a" for MI200 series
```

This installs as `flash_attn` — existing `from flash_attn import ...` imports work unchanged.

Note: Building takes 10-30 minutes. You may need to pin ninja: `pip install ninja==1.10.2.4`.

## requirements.txt Changes

```
# BEFORE
torch
flash-attn

# AFTER (Option A — recommended)
torch
# flash-attn removed; use torch.nn.functional.scaled_dot_product_attention

# AFTER (Option B — if flash_attn import is required)
torch
# flash-attn installed from ROCm/flash-attention source — see 12_flash_attention_rocm.md
```

## Dockerfile Changes

```dockerfile
# BEFORE
RUN pip install flash-attn --no-build-isolation

# AFTER (Option A) — simply remove the line

# AFTER (Option B)
RUN git clone https://github.com/ROCm/flash-attention.git && \
    cd flash-attention && git checkout 3cea2fb && git submodule update --init && \
    GPU_ARCHS="gfx942" python3 setup.py install
```

## Summary

| Scenario | Solution |
|---|---|
| Code calls `flash_attn_func` directly | Replace with `F.scaled_dot_product_attention` |
| Transformers model uses flash attention | Pass `attn_implementation="sdpa"` to `from_pretrained` |
| Library imports `flash_attn` internally (TGI, vLLM) | Build ROCm/flash-attention CK fork from source |
| vLLM on ROCm | vLLM's ROCm build handles this automatically via Triton — no separate install |
