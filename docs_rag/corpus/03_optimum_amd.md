# Running models from Hugging Face

[Hugging Face](https://huggingface.co) hosts the world's largest AI model repository for developers to obtain transformer models. Hugging Face models and tools significantly enhance productivity, performance, and accessibility in developing and deploying AI solutions.

This section describes how to run popular community transformer models from Hugging Face on AMD GPUs.

## Using Hugging Face with Optimum-AMD

Optimum-AMD is the interface between Hugging Face libraries and the ROCm software stack.

For a deeper dive into using Hugging Face libraries on AMD GPUs, refer to the [Optimum-AMD](https://huggingface.co/docs/optimum/main/en/amd/amdgpu/overview) page on Hugging Face for guidance on using Flash Attention 2, GPTQ quantization, and the ONNX Runtime integration.

Hugging Face libraries natively support AMD Instinct GPUs. For other [ROCm-capable hardware](https://rocm.docs.amd.com/projects/install-on-linux/en/docs-7.2.3/reference/system-requirements.html), support is currently not validated, but most features are expected to work without issues.

### Installation

Install Optimum-AMD using pip:

```bash
pip install --upgrade --upgrade-strategy eager optimum[amd]
```

Or, install from source:

```bash
git clone https://github.com/huggingface/optimum-amd.git
cd optimum-amd
pip install -e .
```

## Flash Attention

1. Use [the Hugging Face team's example Dockerfile](https://github.com/huggingface/optimum-amd/blob/main/docker/transformers-pytorch-amd-gpu-flash/Dockerfile) to use Flash Attention with ROCm:

```bash
docker build -f Dockerfile -t transformers_pytorch_amd_gpu_flash .
volume=$PWD
docker run -it --network=host --device=/dev/kfd --device=/dev/dri --group-add=video --ipc=host --cap-add=SYS_PTRACE --security-opt seccomp=unconfined -v $volume:/workspace --name transformer_amd \
transformers_pytorch_amd_gpu_flash:latest
```

2. Use Flash Attention 2 with [Transformers](https://huggingface.co/docs/transformers/perf_infer_gpu_one#flashattention-2) by adding the `use_flash_attention_2` parameter to `from_pretrained()`:

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

## GPTQ

To enable [GPTQ](https://arxiv.org/abs/2210.17323), hosted wheels are available for ROCm.

1. First, install Optimum-AMD (see the Installation section).

2. Install AutoGPTQ using pip. Refer to [AutoGPTQ Installation](https://github.com/AutoGPTQ/AutoGPTQ#Installation) for in-depth guidance:

```bash
pip install auto-gptq --no-build-isolation --extra-index-url https://huggingface.github.io/autogptq-index/whl/rocm573/
```

Or, install from source for AMD GPUs supporting ROCm by specifying `ROCM_VERSION`:

```bash
ROCM_VERSION=6.1 pip install -vvv --no-build-isolation -e .
```

3. Load GPTQ-quantized models in Transformers using the backend [AutoGPTQ library](https://github.com/PanQiWei/AutoGPTQ):

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

## ONNX

Hugging Face Optimum supports [ONNX Runtime](https://onnxruntime.ai) integration. For ONNX models, usage is straightforward.

1. Specify the provider argument in `ORTModel.from_pretrained()`:

```python
from optimum.onnxruntime import ORTModelForSequenceClassification

ort_model = ORTModelForSequenceClassification.from_pretrained(
    provider="ROCMExecutionProvider",
)
```

2. Try running a [BERT text classification](https://huggingface.co/distilbert/distilbert-base-uncased-finetuned-sst-2-english) ONNX model with ROCm:

```python
from optimum.onnxruntime import ORTModelForSequenceClassification
from optimum.pipelines import pipeline
from transformers import AutoTokenizer
import onnxruntime as ort

session_options = ort.SessionOptions()
session_options.log_severity_level = 0

ort_model = ORTModelForSequenceClassification.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english",
    export=True,
    provider="ROCMExecutionProvider",
    session_options=session_options,
)

tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased-finetuned-sst-2-english")

pipe = pipeline(
    task="text-classification",
    model=ort_model,
    tokenizer=tokenizer,
    device="cuda:0",
)

result = pipe("Both the music and visual were astounding, not to mention the actors performance.")
```
