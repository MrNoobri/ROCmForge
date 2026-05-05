# Model Quantization Techniques on AMD ROCm

Quantization reduces model size compared to its native full-precision version, making it easier to fit large models onto GPUs with limited memory. This section explains how to perform LLM quantization using AMD Quark, GPTQ, and bitsandbytes on AMD Instinct hardware.

## AMD Quark (Recommended for AMD)

[AMD Quark](https://quark.docs.amd.com/latest/) offers an efficient and scalable quantization solution tailored to AMD Instinct GPUs. It supports `FP8` and `INT8` quantization for activations, weights, and KV cache, including `FP8` attention. For very large models, it uses a two-level `INT4-FP8` scheme for nearly 4x compression without sacrificing accuracy. Quark scales across multiple GPUs and handles ultra-large models like Llama-3.1-405B. Quantized `FP8` models like Llama, Mixtral, and Grok-1 are available under the AMD organization on Hugging Face and can be deployed via vLLM.

### Installing Quark

```bash
pip install amd-quark
```

### Using Quark for quantization

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from quark.torch.quantization import Config, QuantizationConfig, FP8E4M3PerTensorSpec
from quark.torch import ModelQuantizer, ModelExporter
from quark.torch.export import ExporterConfig, JsonExporterConfig
import torch

MODEL_ID = "meta-llama/Llama-2-70b-chat-hf"
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, device_map="auto", torch_dtype="auto")
model.eval()
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

FP8_PER_TENSOR_SPEC = FP8E4M3PerTensorSpec(observer_method="min_max", is_dynamic=False).to_quantization_spec()
global_quant_config = QuantizationConfig(input_tensors=FP8_PER_TENSOR_SPEC, weight=FP8_PER_TENSOR_SPEC)
quant_config = Config(global_quant_config=global_quant_config, exclude=["lm_head"])

quantizer = ModelQuantizer(quant_config)
quant_model = quantizer.quantize_model(model, calib_dataloader)
```

### Evaluating with vLLM

```python
from vllm import LLM, SamplingParams

llm = LLM(
    model="Llama-2-70b-chat-hf-w-fp8-a-fp8-kvcache-fp8-pertensor",
    kv_cache_dtype="fp8",
    quantization="quark",
)
```

## GPTQ (Post-Training Quantization, int4)

GPTQ quantizes each row of the weight matrix independently to minimize error. Weights are stored as `int4` but restored to `fp16` on the fly during inference, saving ~4x memory with a speedup from lower bandwidth.

### Installing AutoGPTQ for ROCm

```bash
# Pre-built wheel for ROCm
pip install auto-gptq --no-build-isolation --extra-index-url https://huggingface.github.io/autogptq-index/whl/rocm573/

# Or build from source for a specific ROCm version
git clone https://github.com/AutoGPTQ/AutoGPTQ.git && cd AutoGPTQ
PYTORCH_ROCM_ARCH=gfx942 ROCM_VERSION=6.1 pip install .
```

### Using GPTQ via Hugging Face Transformers

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, GPTQConfig

tokenizer = AutoTokenizer.from_pretrained("NousResearch/Llama-2-7b-hf")
gptq_config = GPTQConfig(bits=4, dataset="c4", tokenizer=tokenizer)

quantized_model = AutoModelForCausalLM.from_pretrained(
    "NousResearch/Llama-2-7b-hf",
    device_map="auto",
    quantization_config=gptq_config,
)
quantized_model.save_pretrained("llama-2-7b-gptq")
```

For faster inference on Instinct GPUs, use ExLlama-v2:

```python
gptq_config = GPTQConfig(bits=4, dataset="c4", exllama_config={"version": 2})
```

## bitsandbytes on ROCm

The ROCm-aware bitsandbytes fork (`ROCm/bitsandbytes`) supports 8-bit and 4-bit quantization on AMD Instinct GPUs. The standard pip package targets CUDA — you must build the ROCm fork from source.

### Installing bitsandbytes for ROCm

```bash
git clone --recurse https://github.com/ROCm/bitsandbytes.git
cd bitsandbytes
git checkout rocm_enabled_multi_backend

pip install -r requirements-dev.txt

# Specify your GPU arch (gfx942 = MI300X, gfx90a = MI200)
cmake -DBNB_ROCM_ARCH="gfx942" -DCOMPUTE_BACKEND=hip -S .
make
python setup.py install
```

Verify:

```bash
pip show bitsandbytes
# Version: 0.44.0.dev0 (or similar)
```

### Using bitsandbytes with Transformers on ROCm

Once installed, the API is identical to the CUDA version:

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(load_in_4bit=True)

model = AutoModelForCausalLM.from_pretrained(
    "NousResearch/Llama-2-7b-hf",
    device_map="auto",
    quantization_config=quantization_config,
)
inputs = tokenizer("What is a large language model?", return_tensors="pt").to("cuda")
generated_ids = model.generate(**inputs)
```

## Summary: Which Quantization Tool to Use on AMD

| Tool | Best for | Install complexity |
|---|---|---|
| **AMD Quark** | New AMD deployments, FP8/INT8, vLLM integration | `pip install amd-quark` |
| **AutoGPTQ** | INT4 inference, Transformers integration, ROCm wheels available | Pip or build from source |
| **bitsandbytes (ROCm fork)** | Existing code that uses bitsandbytes API | Build from source required |
| **AWQ + AutoAWQ** | INT4 with Exllama kernels on AMD | See AutoAWQ repo |
