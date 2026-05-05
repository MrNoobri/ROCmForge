# ROCm Dockerfile Migration Guide

## Why `FROM nvidia/cuda` Fails on AMD

NVIDIA CUDA Docker images bundle CUDA runtime libraries (`libcuda.so`, `libcudart.so`, cuDNN, etc.) that only work with NVIDIA drivers. On an AMD system, these libraries are absent and the container cannot start GPU workloads. The AMD GPU runtime depends on `/dev/kfd` and `/dev/dri` — kernel-level device files exposed through the ROCm driver stack.

**Never use `nvidia/cuda` base images on AMD hardware.**

## ROCm Base Image Options

| Image | When to use |
|---|---|
| `rocm/pytorch:latest` | PyTorch workloads — includes ROCm, PyTorch, torchvision, MIOpen |
| `rocm/pytorch:rocm7.2.2_ubuntu24.04_py3.12_pytorch_release_2.9.1` | Pinned version for reproducibility |
| `rocm/dev-ubuntu-22.04:latest` | Minimal ROCm base — install your own Python stack |
| `rocm/dev-ubuntu-24.04:latest` | Minimal ROCm base on Ubuntu 24.04 |
| `vllm-rocm` (build from Dockerfile.rocm) | vLLM serving on ROCm — see `02_vllm_rocm.md` |

## Required `docker run` Flags for AMD

NVIDIA requires `--gpus all`. AMD requires these device flags instead:

```bash
docker run -it \
    --device=/dev/kfd \        # HSA kernel fusion driver — required for ROCm
    --device=/dev/dri \        # Direct Rendering Infrastructure — GPU access
    --group-add video \        # User must be in the video group
    --ipc=host \               # Shared memory for multi-process workloads
    --shm-size 8G \            # Increase shared memory (default 64MB is too small)
    --cap-add=SYS_PTRACE \     # Needed for some profiling tools
    --security-opt seccomp=unconfined \
    rocm/pytorch:latest
```

## Before/After: Migrating a Dockerfile

### Before (NVIDIA/CUDA)

```dockerfile
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y python3 python3-pip
COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY app.py .
CMD ["python3", "app.py"]
```

### After (AMD/ROCm)

```dockerfile
FROM rocm/pytorch:rocm7.2.2_ubuntu22.04_py3.10_pytorch_release_2.9.1

# ROCm image already has Python and PyTorch — just install your extras
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app.py .
CMD ["python3", "app.py"]
```

Key changes:
- `FROM nvidia/cuda:...` → `FROM rocm/pytorch:...`
- Remove any `RUN apt-get install cuda-*` or `RUN pip install torch --index-url .../cu121` lines — ROCm PyTorch is already in the base image
- Remove `flash-attn` from requirements.txt (see `12_flash_attention_rocm.md`)
- Remove `bitsandbytes` from requirements.txt if using pip version — use ROCm fork or AutoGPTQ instead

## Build the ROCm Container

```bash
docker build -t myapp-rocm .

docker run -it \
    --device=/dev/kfd \
    --device=/dev/dri \
    --group-add video \
    --ipc=host \
    --shm-size 8G \
    myapp-rocm
```

## Verifying the GPU is Visible Inside the Container

```bash
# Check ROCm sees the GPU
rocm-smi

# Check PyTorch sees it
python3 -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

On ROCm, `torch.cuda.is_available()` returns `True` — PyTorch aliases `cuda` to the HIP backend, so existing `.cuda()` calls work without code changes.
