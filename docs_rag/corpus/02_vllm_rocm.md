# vLLM Installation with ROCm

vLLM supports AMD GPUs with ROCm 6.2.

## Requirements

- OS: Linux
- Python: 3.9 - 3.12
- GPU: MI200s (gfx90a), MI300 (gfx942), Radeon RX 7900 series (gfx1100)
- ROCm 6.2

Installation options:

1. Build from source with Docker
2. Build from source

## Option 1: Build from source with Docker (recommended)

You can build and install vLLM from source. First, build a Docker image from `Dockerfile.rocm` and launch a container from the image. It is important that the build uses BuildKit. Either set `DOCKER_BUILDKIT=1` when running the build or enable BuildKit in `/etc/docker/daemon.json` and restart the daemon:

```json
{
    "features": {
        "buildkit": true
    }
}
```

`Dockerfile.rocm` uses ROCm 6.2 by default, but also supports ROCm 5.7, 6.0, and 6.1 in older vLLM branches.

### Build arguments

You can customize the Docker build with these arguments:

- `BASE_IMAGE`: base image for `docker build` (PyTorch on ROCm base image).
- `BUILD_FA`: build CK flash-attention. Default is `1`. For Radeon RX 7900 series (gfx1100), set to `0` until flash-attention supports this target.
- `FX_GFX_ARCHS`: GFX architectures used to build CK flash-attention (for example, `gfx90a;gfx942`). Default is `gfx90a;gfx942`.
- `FA_BRANCH`: branch used to build CK flash-attention in ROCm's flash-attention repo. Default is `ae7928c`.
- `BUILD_TRITON`: build Triton flash-attention. Default is `1`.

Pass values with `--build-arg` when running `docker build`.

### Build examples

For ROCm 6.2 on MI200 and MI300 series (defaults):

```bash
DOCKER_BUILDKIT=1 docker build -f Dockerfile.rocm -t vllm-rocm .
```

For ROCm 6.2 on Radeon RX 7900 series (gfx1100), disable CK flash-attention:

```bash
DOCKER_BUILDKIT=1 docker build --build-arg BUILD_FA="0" -f Dockerfile.rocm -t vllm-rocm .
```

### Run the image

```bash
docker run -it \
   --network=host \
   --group-add=video \
   --ipc=host \
   --cap-add=SYS_PTRACE \
   --security-opt seccomp=unconfined \
   --device /dev/kfd \
   --device /dev/dri \
   -v <path/to/model>:/app/model \
   vllm-rocm \
   bash
```

Where `<path/to/model>` is the location where the model is stored (for example, weights for Llama 2 or Llama 3).

## Option 2: Build from source

### 0. Install prerequisites

Skip this step if your environment already has these installed.

- ROCm
- PyTorch

For PyTorch, you can start from a fresh Docker image, such as `rocm/pytorch:rocm6.2_ubuntu20.04_py3.9_pytorch_release_2.3.0` or `rocm/pytorch-nightly`. Alternatively, install PyTorch using wheels from the PyTorch Getting Started guide.

### 1. Install Triton flash-attention for ROCm

Install ROCm's Triton flash-attention (default `triton-mlir` branch) following ROCm/triton instructions. Example:

```bash
python3 -m pip install ninja cmake wheel pybind11
pip uninstall -y triton
git clone https://github.com/OpenAI/triton.git
cd triton
git checkout e192dba
cd python
pip3 install .
cd ../..
```

Note: If you see HTTP issues while downloading packages during Triton build, retry the command. The error is intermittent.

### 2. (Optional) Install CK flash-attention for ROCm

Install ROCm's flash-attention (v2.5.9.post1) from ROCm/flash-attention. Wheels intended for vLLM use are also available under the releases.

Example for ROCm 6.2 on `gfx90a` (find your GFX architecture with `rocminfo | grep gfx`):

```bash
git clone https://github.com/ROCm/flash-attention.git
cd flash-attention
git checkout 3cea2fb
git submodule update --init
GPU_ARCHS="gfx90a" python3 setup.py install
cd ..
```

Note: You might need to downgrade `ninja` to 1.10 if it is not used when compiling flash-attention-2 (for example, `pip install ninja==1.10.2.4`).

### 3. Build vLLM

Example build for ROCm 6.2:

```bash
pip install --upgrade pip

# Install PyTorch
pip uninstall torch -y
pip install --no-cache-dir --pre torch==2.6.0.dev20240918 --index-url https://download.pytorch.org/whl/nightly/rocm6.2

# Build and install AMD SMI
pip install /opt/rocm/share/amd_smi

# Install dependencies
pip install --upgrade numba scipy huggingface-hub[cli]
pip install "numpy<2"
pip install -r requirements-rocm.txt

# Build vLLM for MI210/MI250/MI300
export PYTORCH_ROCM_ARCH="gfx90a;gfx942"
python3 setup.py develop
```

This may take 5-10 minutes. Currently, `pip install .` does not work for ROCm installation.

## Tips

- Triton flash-attention is used by default. For benchmarking, run a warm-up step before collecting performance numbers.
- Triton flash-attention does not currently support sliding window attention. If using half precision, use CK flash-attention for sliding window support.
- To use CK flash-attention or PyTorch naive attention, set `export VLLM_USE_TRITON_FLASH_ATTN=0` to disable Triton flash-attention.
- The ROCm version of PyTorch should ideally match the ROCm driver version.
- For MI300x (gfx942) users, see the MI300x tuning guide and vLLM performance optimization for system and workflow tuning tips.
