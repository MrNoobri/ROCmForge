# Using Hugging Face libraries on AMD GPUs

Hugging Face libraries support AMD Instinct MI210, MI250, and MI300 GPUs natively. For other ROCm-powered GPUs, support has not been validated yet, but most features are expected to work.

## Flash Attention 2

Flash Attention 2 is available on ROCm (validated on MI210, MI250, and MI300) through the [ROCm/flash-attention](https://github.com/ROCm/flash-attention) library, and can be used in [Transformers](https://huggingface.co/docs/transformers/perf_infer_gpu_one#flashattention-2):

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

We recommend using [this example Dockerfile](https://github.com/huggingface/optimum-amd/blob/main/docker/transformers-pytorch-amd-gpu-flash/Dockerfile) to use Flash Attention on ROCm, or follow the [official installation instructions](https://github.com/ROCm/flash-attention#amd-gpurocm-support).

## GPTQ quantization

[GPTQ](https://arxiv.org/abs/2210.17323) quantized models can be loaded in Transformers using the [AutoGPTQ](https://github.com/PanQiWei/AutoGPTQ) library:

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

Hosted wheels are available for ROCm; see the [installation instructions](https://github.com/PanQiWei/AutoGPTQ#installation).

## Text Generation Inference library

Hugging Face's [Text Generation Inference](https://huggingface.co/docs/text-generation-inference/index) library (TGI) is designed for low-latency LLM serving and natively supports AMD Instinct MI210, MI250, and MI300 GPUs. See the [Quick Tour](https://huggingface.co/docs/text-generation-inference/quicktour) for details.

Using TGI on ROCm with AMD Instinct MI210 or MI250 or MI300 GPUs is as simple as using the Docker image [`ghcr.io/huggingface/text-generation-inference:latest-rocm`](https://huggingface.co/docs/text-generation-inference/quicktour).

Detailed benchmarks of Text Generation Inference on MI300 GPUs will be published soon.

## ONNX Runtime integration

[Optimum](https://huggingface.co/docs/optimum/onnxruntime/quickstart) supports running [Transformers](https://github.com/huggingface/transformers) and [Diffusers](https://github.com/huggingface/diffusers) models through [ONNX Runtime](https://onnxruntime.ai/) on ROCm-powered AMD GPUs:

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

Check out more details in [this guide](https://huggingface.co/docs/optimum/onnxruntime/usage_guides/amdgpu).

## Bitsandbytes quantization

[Bitsandbytes](https://github.com/TimDettmers/bitsandbytes) (integrated in [Transformers](https://huggingface.co/docs/transformers/perf_infer_gpu_one#bitsandbytes) and [Text Generation Inference](https://huggingface.co/docs/text-generation-inference/conceptual/quantization#quantization-with-bitsandbytes)) does not officially support ROCm yet. Validation on ROCm and through Hugging Face libraries is in progress.

For now, advanced users can try the [ROCm/bitsandbytes](https://github.com/ROCm/bitsandbytes/tree/rocm_enabled) fork. See [this issue comment](https://github.com/TimDettmers/bitsandbytes/pull/756#issuecomment-2067761175) for more details.

## AWQ quantization

[AWQ](https://arxiv.org/abs/2306.00978) quantization, supported in [Transformers](https://huggingface.co/docs/transformers/main_classes/quantization#awq-integration) and [Text Generation Inference](https://huggingface.co/docs/text-generation-inference/basic_tutorials/preparing_model#quantization), is supported on AMD GPUs using Exllama kernels. With recent optimizations, the AWQ model is converted to Exllama/GPTQ format at load time, allowing ROCm devices to benefit from AWQ checkpoints and ExllamaV2 kernels.

See [AutoAWQ](https://github.com/casper-hansen/AutoAWQ/pull/313) for more details.

Note: Ensure you have the same PyTorch version that was used to build the kernels.
