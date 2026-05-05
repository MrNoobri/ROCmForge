# bitsandbytes — API Reference and Quantization Concepts

[bitsandbytes](https://github.com/TimDettmers/bitsandbytes) provides 8-bit and 4-bit quantization for large models, reducing memory usage significantly. It integrates directly with Hugging Face Transformers via `BitsAndBytesConfig`.

**ROCm note:** The standard pip release targets CUDA. For AMD GPU support, use the ROCm fork — see `10_quantization_rocm.md` for install steps. The API shown here is identical across both backends.

## Basic Usage

Install:

```bash
pip install transformers accelerate bitsandbytes>0.37.0
```

## 8-bit Quantization (LLM.int8())

Halves memory usage. For large models, use `device_map="auto"`:

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(load_in_8bit=True)

model_8bit = AutoModelForCausalLM.from_pretrained(
    "bigscience/bloom-1b7",
    quantization_config=quantization_config,
)
```

Check memory footprint:

```python
print(model.get_memory_footprint())
```

## 4-bit Quantization (QLoRA)

4-bit compresses models further. Commonly used with QLoRA for fine-tuning quantized LLMs:

```python
import torch
from transformers import BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,  # faster computation
    bnb_4bit_quant_type="nf4",              # Normal Float 4, optimal for normally distributed weights
    bnb_4bit_use_double_quant=True,          # nested quantization saves ~0.4 bits/param
)
```

## Loading a Pre-quantized Model

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained(
    "{your_username}/bloom-560m-8bit",
    device_map="auto",
)
```

No need to pass `load_in_8bit` or `load_in_4bit` — the config is stored with the model.

## Dequantizing

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained(
    "facebook/opt-125m",
    quantization_config=BitsAndBytesConfig(load_in_4bit=True),
)
model.dequantize()
```

## Advanced: Outlier Threshold

For unstable models, tune `llm_int8_threshold` (default 6.0):

```python
quantization_config = BitsAndBytesConfig(
    llm_int8_threshold=10.0,
    llm_int8_enable_fp32_cpu_offload=True,
)
```

## Advanced: Skip Module Conversion

Some modules (e.g., `lm_head`) should not be quantized:

```python
quantization_config = BitsAndBytesConfig(
    llm_int8_skip_modules=["lm_head"],
)
```

## Migration Recommendation

If migrating a CUDA project that uses bitsandbytes to AMD/ROCm, the recommended path is:
- **Optimum-AMD with AutoGPTQ** — native Triton/ROCm support, no build-from-source needed
- **AMD Quark** — AMD's own quantization tool, supports FP8/INT8/INT4, integrates with vLLM

See `10_quantization_rocm.md` for details on both alternatives.
