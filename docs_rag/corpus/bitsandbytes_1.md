# bitsandbytes

[bitsandbytes](https://github.com/TimDettmers/bitsandbytes) is an easy option for quantizing a model to 8-bit and 4-bit. 8-bit quantization multiplies outliers in fp16 with non-outliers in int8, converts the non-outlier values back to fp16, and then adds them together to return the weights in fp16. This reduces the degradative effect outlier values have on a model’s performance. 4-bit quantization compresses a model even further, and it is commonly used with [QLoRA](https://hf.co/papers/2305.14314) to fine-tune quantized LLMs.

To use bitsandbytes, make sure you have the following libraries installed:

```bash
pip install transformers accelerate bitsandbytes>0.37.0
```

Tip: bitsandbytes is being refactored to support multiple backends beyond CUDA. ROCm (AMD GPU) and Intel CPU implementations are mature, with Intel XPU in progress and Apple Silicon support expected by Q4/Q1. For installation instructions and the latest backend updates, visit [this link](https://huggingface.co/docs/bitsandbytes/main/en/installation#multi-backend).

We value your feedback to help identify bugs before the full release. Check out [these docs](https://huggingface.co/docs/bitsandbytes/main/en/non_cuda_backends) for more details and feedback links.

Now you can quantize a model by passing a `BitsAndBytesConfig` to [from_pretrained()](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/model#transformers.PreTrainedModel.from_pretrained). This works for any model in any modality, as long as it supports loading with Accelerate and contains `torch.nn.Linear` layers.

Quantizing a model in 8-bit halves memory usage, and for large models, set `device_map="auto"` to efficiently use available GPUs:

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(load_in_8bit=True)

model_8bit = AutoModelForCausalLM.from_pretrained(
    "bigscience/bloom-1b7",
    quantization_config=quantization_config,
)
```

By default, other modules such as `torch.nn.LayerNorm` are converted to `torch.float16`. You can change the data type of these modules with `torch_dtype`. Setting `torch_dtype="auto"` loads the model using the data type defined in the model’s `config.json` file.

```python
import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(load_in_8bit=True)

model_8bit = AutoModelForCausalLM.from_pretrained(
    "facebook/opt-350m",
    quantization_config=quantization_config,
    torch_dtype="auto",
)
model_8bit.model.decoder.layers[-1].final_layer_norm.weight.dtype
```

Once a model is quantized to 8-bit, you cannot push the quantized weights to the Hub unless you are using the latest versions of Transformers and bitsandbytes. If you have the latest versions, then you can push the 8-bit model to the Hub with [push_to_hub()](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/model#transformers.utils.PushToHubMixin.push_to_hub). The quantization config file is pushed first, followed by the quantized model weights.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(load_in_8bit=True)

model = AutoModelForCausalLM.from_pretrained(
    "bigscience/bloom-560m",
    quantization_config=quantization_config,
)
tokenizer = AutoTokenizer.from_pretrained("bigscience/bloom-560m")

model.push_to_hub("bloom-560m-8bit")
```

Tip: Training with 8-bit and 4-bit weights is only supported for training extra parameters.

You can check your memory footprint with `get_memory_footprint`:

```python
print(model.get_memory_footprint())
```

Quantized models can be loaded from [from_pretrained()](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/model#transformers.PreTrainedModel.from_pretrained) without specifying `load_in_8bit` or `load_in_4bit`:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained(
    "{your_username}/bloom-560m-8bit",
    device_map="auto",
)
```

## 8-bit (LLM.int8() algorithm)

Learn more about 8-bit quantization in this [blog post](https://huggingface.co/blog/hf-bitsandbytes-integration).

This section explores features of 8-bit models, such as offloading, outlier thresholds, skipping module conversion, and fine-tuning.

### Offloading

8-bit models can offload weights between CPU and GPU to fit very large models into memory. The weights dispatched to the CPU are stored in float32 and are not converted to 8-bit. For example, to enable offloading for [bigscience/bloom-1b7](https://huggingface.co/bigscience/bloom-1b7), start by creating a [BitsAndBytesConfig](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/quantization#transformers.BitsAndBytesConfig):

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(llm_int8_enable_fp32_cpu_offload=True)
```

Design a custom device map to fit everything on your GPU except for `lm_head`, which you dispatch to the CPU:

```python
device_map = {
    "transformer.word_embeddings": 0,
    "transformer.word_embeddings_layernorm": 0,
    "lm_head": "cpu",
    "transformer.h": 0,
    "transformer.ln_f": 0,
}
```

Now load your model with the custom `device_map` and `quantization_config`:

```python
model_8bit = AutoModelForCausalLM.from_pretrained(
    "bigscience/bloom-1b7",
    torch_dtype="auto",
    device_map=device_map,
    quantization_config=quantization_config,
)
```

### Outlier threshold

An outlier is a hidden state value greater than a certain threshold, computed in fp16. Values are usually normally distributed ([-3.5, 3.5]), but large models can have wider ranges ([-60, 6] or [6, 60]). 8-bit quantization works well for values around 5; beyond that, there is a significant performance penalty. A good default threshold is 6, but a lower threshold may be needed for more unstable models (small models or fine-tuning).

Experiment with `llm_int8_threshold` in [BitsAndBytesConfig](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/quantization#transformers.BitsAndBytesConfig):

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig

model_id = "bigscience/bloom-1b7"

quantization_config = BitsAndBytesConfig(
    llm_int8_threshold=10.0,
    llm_int8_enable_fp32_cpu_offload=True,
)

model_8bit = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype="auto",
    device_map=device_map,
    quantization_config=quantization_config,
)
```

### Skip module conversion

For some models, like Jukebox, you do not need to quantize every module to 8-bit, which can cause instability. With Jukebox, there are several `lm_head` modules that should be skipped using `llm_int8_skip_modules` in [BitsAndBytesConfig](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/quantization#transformers.BitsAndBytesConfig):

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

model_id = "bigscience/bloom-1b7"

quantization_config = BitsAndBytesConfig(
    llm_int8_skip_modules=["lm_head"],
)

model_8bit = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype="auto",
    device_map="auto",
    quantization_config=quantization_config,
)
```

### Finetuning

With the [PEFT](https://github.com/huggingface/peft) library, you can fine-tune large models like [flan-t5-large](https://huggingface.co/google/flan-t5-large) and [facebook/opt-6.7b](https://huggingface.co/facebook/opt-6.7b) with 8-bit quantization. You do not need to pass `device_map` for training because it loads your model on a GPU automatically. You can still customize the device map with `device_map` if you want to (`device_map="auto"` should only be used for inference).

## 4-bit (QLoRA algorithm)

Try 4-bit quantization in this [notebook](https://colab.research.google.com/drive/1ge2F1QSK8Q7h0hn3YKuBCOAS0bK8E0wf) and learn more in this [blog post](https://huggingface.co/blog/4bit-transformers-bitsandbytes).

This section explores features of 4-bit models, such as changing the compute data type, using Normal Float 4 (NF4), and using nested quantization.

### Compute data type

To speed up computation, you can change the data type from float32 (default) to bf16 using `bnb_4bit_compute_dtype` in [BitsAndBytesConfig](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/quantization#transformers.BitsAndBytesConfig):

```python
import torch
from transformers import BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
)
```

### Normal Float 4 (NF4)

NF4 is a 4-bit data type from the [QLoRA](https://hf.co/papers/2305.14314) paper, adapted for weights initialized from a normal distribution. Use NF4 for training 4-bit base models. Configure this with `bnb_4bit_quant_type` in [BitsAndBytesConfig](https://huggingface.co/docs/transformers/v4.49.0/en/main_classes/quantization#transformers.BitsAndBytesConfig):

```python
from transformers import BitsAndBytesConfig

nf4_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
)

model_nf4 = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype="auto",
    quantization_config=nf4_config,
)
```

For inference, `bnb_4bit_quant_type` does not have a huge impact on performance. To remain consistent with model weights, use matching `bnb_4bit_compute_dtype` and `torch_dtype` values.

### Nested quantization

Nested quantization saves additional memory at no added performance cost. It performs a second quantization of already quantized weights to save ~0.4 bits per parameter. For example, with nested quantization you can fine-tune a [Llama-13b](https://huggingface.co/meta-llama/Llama-2-13b-chat-hf) model on a 16GB NVIDIA T4 GPU with sequence length 1024, batch size 1, and gradient accumulation for 4 steps.

```python
from transformers import BitsAndBytesConfig

double_quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
)

model_double_quant = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-2-13b-chat-hf",
    torch_dtype="auto",
    quantization_config=double_quant_config,
)
```

## Dequantizing bitsandbytes models

Once quantized, you can dequantize the model to the original precision, which might result in a small quality loss. Make sure you have enough GPU RAM to fit the dequantized model.

```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig, AutoTokenizer

model_id = "facebook/opt-125m"

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=BitsAndBytesConfig(load_in_4bit=True),
)
tokenizer = AutoTokenizer.from_pretrained(model_id)

model.dequantize()

text = tokenizer("Hello my name is", return_tensors="pt").to(0)

out = model.generate(**text)
print(tokenizer.decode(out[0]))
```
