# Model quantization techniques

Quantization reduces the model size compared to its native full-precision version, making it easier to fit large models onto GPUs with limited memory usage. This section explains how to perform LLM quantization using AMD Quark, GPTQ, and bitsandbytes on AMD Instinct hardware.

## AMD Quark

[AMD Quark](https://quark.docs.amd.com/latest/) offers an efficient and scalable quantization solution tailored to AMD Instinct GPUs. It supports `FP8` and `INT8` quantization for activations, weights, and KV cache, including `FP8` attention. For very large models, it uses a two-level `INT4-FP8` scheme (store weights in `INT4` while computing with `FP8`) for nearly 4x compression without sacrificing accuracy. Quark scales across multiple GPUs and handles ultra-large models like Llama-3.1-405B. Quantized `FP8` models like Llama, Mixtral, and Grok-1 are available under the [AMD organization on Hugging Face](https://huggingface.co/collections/amd/quark-quantized-ocp-fp8-models-66db7936d18fcbaf95d4405c) and can be deployed via [vLLM](https://github.com/vllm-project/vllm/tree/main/vllm).

### Installing Quark

The latest release of Quark can be installed with pip:

```bash
pip install amd-quark
```

For detailed installation instructions, refer to the [Quark documentation](https://quark.docs.amd.com/latest/install.html).

### Using Quark for quantization

1. Load the pretrained model and tokenizer using Hugging Face Transformers.

```python
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_ID = "meta-llama/Llama-2-70b-chat-hf"
MAX_SEQ_LEN = 512

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, device_map="auto", torch_dtype="auto",
)
model.eval()

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, model_max_length=MAX_SEQ_LEN)
tokenizer.pad_token = tokenizer.eos_token
```

2. Prepare the calibration DataLoader (static quantization requires calibration data).

```python
from datasets import load_dataset
from torch.utils.data import DataLoader

BATCH_SIZE = 1
NUM_CALIBRATION_DATA = 512

dataset = load_dataset("mit-han-lab/pile-val-backup", split="validation")
text_data = dataset["text"][:NUM_CALIBRATION_DATA]

tokenized_outputs = tokenizer(
    text_data, return_tensors="pt", padding=True, truncation=True, max_length=MAX_SEQ_LEN
)
calib_dataloader = DataLoader(
    tokenized_outputs["input_ids"], batch_size=BATCH_SIZE, drop_last=True
)
```

3. Define the quantization configuration.

```python
from quark.torch.quantization import (
    Config,
    QuantizationConfig,
    FP8E4M3PerTensorSpec,
)

# Define fp8/per-tensor/static spec.
FP8_PER_TENSOR_SPEC = FP8E4M3PerTensorSpec(
    observer_method="min_max",
    is_dynamic=False,
).to_quantization_spec()

# Define global quantization config, input tensors and weight apply FP8_PER_TENSOR_SPEC.
global_quant_config = QuantizationConfig(
    input_tensors=FP8_PER_TENSOR_SPEC,
    weight=FP8_PER_TENSOR_SPEC,
)

# Define quantization config for kv-cache layers, output tensors apply FP8_PER_TENSOR_SPEC.
KV_CACHE_SPEC = FP8_PER_TENSOR_SPEC
kv_cache_layer_names_for_llama = ["*k_proj", "*v_proj"]
kv_cache_quant_config = {
    name: QuantizationConfig(
        input_tensors=global_quant_config.input_tensors,
        weight=global_quant_config.weight,
        output_tensors=KV_CACHE_SPEC,
    )
    for name in kv_cache_layer_names_for_llama
}
layer_quant_config = kv_cache_quant_config.copy()

EXCLUDE_LAYERS = ["lm_head"]
quant_config = Config(
    global_quant_config=global_quant_config,
    layer_quant_config=layer_quant_config,
    kv_cache_quant_config=kv_cache_quant_config,
    exclude=EXCLUDE_LAYERS,
)
```

4. Quantize the model and export.

```python
import torch
from quark.torch import ModelQuantizer, ModelExporter
from quark.torch.export import ExporterConfig, JsonExporterConfig

# Apply quantization.
quantizer = ModelQuantizer(quant_config)
quant_model = quantizer.quantize_model(model, calib_dataloader)

# Freeze quantized model to export.
freezed_model = quantizer.freeze(model)

# Define export config.
LLAMA_KV_CACHE_GROUP = ["*k_proj", "*v_proj"]
export_config = ExporterConfig(json_export_config=JsonExporterConfig())
export_config.json_export_config.kv_cache_group = LLAMA_KV_CACHE_GROUP

EXPORT_DIR = MODEL_ID.split("/")[1] + "-w-fp8-a-fp8-kvcache-fp8-pertensor"
exporter = ModelExporter(config=export_config, export_dir=EXPORT_DIR)
with torch.no_grad():
    exporter.export_safetensors_model(
        freezed_model, quant_config=quant_config, tokenizer=tokenizer
    )
```

### Evaluating the quantized model with vLLM

The exported Quark-quantized model can be loaded directly by vLLM for inference. Specify the model path, the quantization method (`quantization='quark'`), and the KV cache data type (`kv_cache_dtype='fp8'`). Use `LLM` to load the model:

```python
from vllm import LLM, SamplingParams

# Sample prompts.
prompts = [
    "Hello, my name is",
    "The president of the United States is",
    "The capital of France is",
    "The future of AI is",
]

# Create a sampling params object.
sampling_params = SamplingParams(temperature=0.8, top_p=0.95)

# Create an LLM.
llm = LLM(
    model="Llama-2-70b-chat-hf-w-fp8-a-fp8-kvcache-fp8-pertensor",
    kv_cache_dtype="fp8",
    quantization="quark",
)

# Generate texts from the prompts.
outputs = llm.generate(prompts, sampling_params)

print("\nGenerated Outputs:\n" + "-" * 60)
for output in outputs:
    prompt = output.prompt
    generated_text = output.outputs[0].text
    print(f"Prompt:    {prompt!r}")
    print(f"Output:    {generated_text!r}")
    print("-" * 60)
```

You can also evaluate the quantized model’s accuracy on standard benchmarks using [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness). Pass vLLM arguments to `lm_eval` via `--model_args`:

```bash
lm_eval --model vllm \
  --model_args pretrained=Llama-2-70b-chat-hf-w-fp8-a-fp8-kvcache-fp8-pertensor,kv_cache_dtype='fp8',quantization='quark' \
  --tasks gsm8k
```

This provides a standardized way to measure the performance impact of quantization.

## GPTQ

GPTQ is a post-training quantization technique where each row of the weight matrix is quantized independently to find a version of the weights that minimizes error. These weights are quantized to `int4` but are restored to `fp16` on the fly during inference. This can save memory by a factor of four. A speedup in inference is expected because GPTQ models use a lower bit width, which takes less time to communicate.

Before setting up the GPTQ configuration in Transformers, ensure the [AutoGPTQ](https://github.com/AutoGPTQ/AutoGPTQ) library is installed.

### Installing AutoGPTQ

The AutoGPTQ library implements the GPTQ algorithm.

1. Install the latest stable release from pip.

```bash
# This will install a pre-built wheel for a specific ROCm version.
pip install auto-gptq --no-build-isolation --extra-index-url https://huggingface.github.io/autogptq-index/whl/rocm573/
```

Or, install AutoGPTQ from source for the appropriate ROCm version (for example, ROCm 6.1).

```bash
# Clone the source code.
git clone https://github.com/AutoGPTQ/AutoGPTQ.git
cd AutoGPTQ

# Speed up compilation by specifying PYTORCH_ROCM_ARCH to target device.
PYTORCH_ROCM_ARCH=gfx942 ROCM_VERSION=6.1 pip install .
```

2. Run `pip show auto-gptq` to verify the installation. Output should look like:

```text
Name: auto-gptq
Version: 0.8.0.dev0+rocm6.1
...
```

### Using GPTQ with AutoGPTQ

1. Run the following code snippet.

```python
from transformers import AutoTokenizer, TextGenerationPipeline
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

base_model_name = "NousResearch/Llama-2-7b-hf"
quantized_model_name = "llama-2-7b-hf-gptq"

tokenizer = AutoTokenizer.from_pretrained(base_model_name, use_fast=True)
examples = [
    tokenizer(
        "auto-gptq is an easy-to-use model quantization library with user-friendly apis, based on GPTQ algorithm."
    )
]
print(examples)
```

The resulting examples should be a list of dictionaries with `input_ids` and `attention_mask` keys.

2. Set up the quantization configuration.

```python
quantize_config = BaseQuantizeConfig(
    bits=4,          # quantize model to 4-bit
    group_size=128,  # recommended value
    desc_act=False,
)
```

3. Load the non-quantized model and run quantization.

```python
from auto_gptq import AutoGPTQForCausalLM

base_model = AutoGPTQForCausalLM.from_pretrained(
    base_model_name, quantize_config, device_map="auto"
)
base_model.quantize(examples)

# Save quantized model.
base_model.save_quantized(quantized_model_name)
```

### Using GPTQ with Hugging Face Transformers

1. Create a `GPTQConfig` instance and set the number of bits and calibration dataset.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, GPTQConfig

base_model_name = "NousResearch/Llama-2-7b-hf"
tokenizer = AutoTokenizer.from_pretrained(base_model_name)

gptq_config = GPTQConfig(bits=4, dataset="c4", tokenizer=tokenizer)
```

2. Load a model to quantize and pass `gptq_config` to `from_pretrained()`. Set `device_map="auto"` to offload to available GPUs.

```python
quantized_model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    device_map="auto",
    quantization_config=gptq_config,
)
```

3. Push the model and tokenizer to the Hub, or save locally.

```python
quantized_model.push_to_hub("llama-2-7b-hf-gptq")
tokenizer.push_to_hub("llama-2-7b-hf-gptq")
```

Or save locally:

```python
quantized_model.save_pretrained("llama-2-7b-gptq")
tokenizer.save_pretrained("llama-2-7b-gptq")
```

### ExLlama-v2 support

ExLlama is a Python/C++/CUDA implementation of the Llama model designed for faster inference with 4-bit GPTQ weights. The ExLlama kernel is activated by default when users create a `GPTQConfig`. For faster inference on Instinct GPUs, use ExLlama-v2 by configuring `exllama_config`:

```python
from transformers import AutoModelForCausalLM, GPTQConfig

base_model_name = "NousResearch/Llama-2-7b-hf"

gptq_config = GPTQConfig(bits=4, dataset="c4", exllama_config={"version": 2})

quantized_model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    device_map="auto",
    quantization_config=gptq_config,
)
```

## bitsandbytes

The [ROCm-aware bitsandbytes](https://github.com/ROCm/bitsandbytes) library is a lightweight Python wrapper around CUDA custom functions, including 8-bit optimizers, matrix multiplication, and 8-bit/4-bit quantization functions. It includes quantization primitives for 8-bit and 4-bit operations through `bitsandbytes.nn.Linear8bitLt` and `bitsandbytes.nn.Linear4bit`, and 8-bit optimizers through `bitsandbytes.optim`. These modules are supported on AMD Instinct GPUs.

### Installing bitsandbytes

1. Install bitsandbytes for ROCm 6.0 (and later).

```bash
# Clone the github repo
git clone --recurse https://github.com/ROCm/bitsandbytes.git
cd bitsandbytes
git checkout rocm_enabled_multi_backend

# Install dependencies
pip install -r requirements-dev.txt

# Use -DBNB_ROCM_ARCH to specify target GPU arch
cmake -DBNB_ROCM_ARCH="gfx942" -DCOMPUTE_BACKEND=hip -S .

# Compile the project
make

# Install
python setup.py install
```

2. Run `pip show bitsandbytes` to verify the installation. Output should look like:

```text
Name: bitsandbytes
Version: 0.44.0.dev0
...
```

### Using bitsandbytes primitives

```python
import bitsandbytes as bnb

# Use Int8 Matrix Multiplication
bnb.matmul(..., threshold=6.0)

# Use bitsandbytes 8-bit Optimizers
adam = bnb.optim.Adam8bit(model.parameters(), lr=0.001, betas=(0.9, 0.995))
```

### Using bitsandbytes with Hugging Face Transformers

To load a Transformers model in 4-bit, set `load_in_4bit=True` in `BitsAndBytesConfig`.

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

base_model_name = "NousResearch/Llama-2-7b-hf"
quantization_config = BitsAndBytesConfig(load_in_4bit=True)

bnb_model_4bit = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    device_map="auto",
    quantization_config=quantization_config,
)

print(bnb_model_4bit.get_memory_footprint())
```

To load a model in 8-bit for inference, use `load_in_8bit`.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

base_model_name = "NousResearch/Llama-2-7b-hf"

tokenizer = AutoTokenizer.from_pretrained(base_model_name)
quantization_config = BitsAndBytesConfig(load_in_8bit=True)

bnb_model_8bit = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    device_map="auto",
    quantization_config=quantization_config,
)

prompt = "What is a large language model?"
inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

generated_ids = bnb_model_8bit.generate(**inputs)
outputs = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)
```
