# PyTorch on ROCm Installation

PyTorch is an open-source tensor library for deep learning. PyTorch on ROCm provides mixed-precision and large-scale training using AMD MIOpen and RCCL libraries.

## Install PyTorch

Three options are available:

- Use a prebuilt Docker image with PyTorch pre-installed (recommended)
- Use a wheels package
- Build from source

## Option 1: Prebuilt Docker Image (Recommended)

Pull the latest ROCm-tested PyTorch image:

```bash
docker pull rocm/pytorch:latest
```

Start a container:

```bash
docker run -it \
    --cap-add=SYS_PTRACE \
    --security-opt seccomp=unconfined \
    --device=/dev/kfd \
    --device=/dev/dri \
    --group-add video \
    --ipc=host \
    --shm-size 8G \
    rocm/pytorch:latest
```

## Validated Docker Image Tags (ROCm 7.2.2)

| PyTorch | Python | Docker tag |
|---|---|---|
| 2.9.1 | 3.12 | `rocm/pytorch:rocm7.2.2_ubuntu24.04_py3.12_pytorch_release_2.9.1` |
| 2.9.1 | 3.10 | `rocm/pytorch:rocm7.2.2_ubuntu22.04_py3.10_pytorch_release_2.9.1` |
| 2.8.0 | 3.12 | `rocm/pytorch:rocm7.2.2_ubuntu24.04_py3.12_pytorch_release_2.8.0` |
| 2.8.0 | 3.10 | `rocm/pytorch:rocm7.2.2_ubuntu22.04_py3.10_pytorch_release_2.8.0` |
| 2.7.1 | 3.12 | `rocm/pytorch:rocm7.2.2_ubuntu24.04_py3.12_pytorch_release_2.7.1` |
| 2.7.1 | 3.10 | `rocm/pytorch:rocm7.2.2_ubuntu22.04_py3.10_pytorch_release_2.7.1` |

## Option 2: Wheels Package

Install dependencies and then install from the PyTorch ROCm wheel index:

```bash
sudo apt update
sudo apt install libjpeg-dev python3-dev python3-pip
pip3 install wheel setuptools
pip3 install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/rocm7.2
```

Select Linux, Python, pip, and ROCm at pytorch.org/get-started/locally/ for the current stable command.

## Verify Installation

```bash
# Check PyTorch is importable
python3 -c 'import torch' 2> /dev/null && echo 'Success' || echo 'Failure'

# Check GPU is visible
python3 -c 'import torch; print(torch.cuda.is_available())'
```

On ROCm, `torch.cuda.is_available()` returns `True` because PyTorch aliases the `cuda` device to the HIP backend.

## Troubleshooting

**`hipErrorNoBinaryForGPU: Unable to find code object for all current devices!`**

The installed PyTorch build does not support your GPU architecture.

1. Find your gfx target:
```bash
rocminfo | grep gfx
```

2. Check what PyTorch was compiled for:
```bash
TORCHDIR=$( dirname $( python3 -c 'import torch; print(torch.__file__)' ) )
llvm-readobj --offloading $TORCHDIR/lib/libtorch_hip.so
```

Use a Docker image or wheel that matches your `gfx` target (e.g., `gfx90a` = MI200, `gfx942` = MI300X).

**`Unable to access Docker or GPU in user accounts`**

Ensure your user is in the `docker`, `video`, and `render` Linux groups.

**Setting the ROCm architecture before compiling custom extensions:**

```bash
export PYTORCH_ROCM_ARCH=gfx942   # MI300X
# or gfx90a for MI200 series
```
