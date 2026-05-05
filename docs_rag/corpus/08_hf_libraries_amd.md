# Using Hugging Face Libraries on AMD GPUs

Hugging Face libraries support AMD Instinct MI210, MI250, and MI300 GPUs natively. For other ROCm-powered GPUs, support has not been validated yet, but most features are expected to work.

## Flash Attention 2

Flash Attention 2 is available on ROCm (validated on MI210, MI250, and MI300) through the [ROCm/flash-attention](https://github.com/ROCm/flash-attention) library, and can be used in Transformers:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LlamaForCausalLM

tokenizer = AutoTokenizer.from_pretrained("tiiuae/falcon-7b")

with torch.device("cuda"):
    model = AutoModelForCausalLM.from_pretrained(
        "tiiuae/falcon-7b",
        torch_dtype=torch.float16,
        use_flash_attention_2=True,
)
```

We recommend using the example Dockerfile from the optimum-amd repo to use Flash Attention on ROCm, or follow the official installation instructions.

## GPTQ quantization

GPTQ quantized models can be loaded in Transformers using the AutoGPTQ library:

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LlamaForCausalLM

tokenizer = AutoTokenizer.from_pretrained("TheBloke/Llama-2-7B-Chat-GPTQ")

with torch.device("cuda"):
    model = AutoModelForCausalLM.from_pretrained(
        "TheBloke/Llama-2-7B-Chat-GPTQ",
        torch_dtype=torch.float16,
    )
```

Hosted wheels are available for ROCm; see the AutoGPTQ installation instructions.

## Text Generation Inference library

Hugging Face's Text Generation Inference (TGI) library natively supports AMD Instinct MI210, MI250, and MI300 GPUs. See `07_tgi_amd.md` for AMD-specific setup. Note: for new projects, vLLM on ROCm is the recommended serving stack (see `02_vllm_rocm.md`).

## ONNX Runtime integration

Optimum supports running Transformers and Diffusers models through ONNX Runtime on ROCm-powered AMD GPUs:

```python
from transformers import AutoTokenizer
from optimum.onnxruntime import ORTModelForSequenceClassification

tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased-finetuned-sst-2-english")

ort_model = ORTModelForSequenceClassification.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english",
    export=True,
    provider="ROCMExecutionProvider",
)

inp = tokenizer(
    "Both the music and visual were astounding, not to mention the actors performance.",
    return_tensors="np",
)
result = ort_model(**inp)
```

## Bitsandbytes quantization

**Note on ROCm support:** Earlier versions of bitsandbytes did not officially support ROCm. The ROCm fork (`ROCm/bitsandbytes`) is now functional and supports 4-bit and 8-bit quantization on AMD Instinct GPUs — see `10_quantization_rocm.md` for the installation path.

For migration purposes: if a CUDA project uses `bitsandbytes`, the recommended AMD alternative is **Hugging Face Optimum-AMD** with AutoGPTQ or AMD Quark (see `10_quantization_rocm.md`). These have native Triton/ROCm support and do not require building from source.

## AWQ quantization

AWQ quantization, supported in Transformers and TGI, is supported on AMD GPUs using Exllama kernels. With recent optimizations, the AWQ model is converted to Exllama/GPTQ format at load time, allowing ROCm devices to benefit from AWQ checkpoints and ExllamaV2 kernels.

See AutoAWQ for more details. Ensure you have the same PyTorch version that was used to build the kernels.
