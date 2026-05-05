Here is the comprehensive NVIDIA to AMD Migration Cheatsheet for PyTorch and JAX workloads.

### The Rosetta Stone: CUDA to ROCm Key Patterns

Use this quick-reference table to map the proprietary NVIDIA stack to the open-source AMD ROCm ecosystem.

| Domain | NVIDIA (CUDA) | AMD (ROCm) | Notes |
| :--- | :--- | :--- | :--- |
| **System Monitor** | `nvidia-smi` | `rocm-smi` | `rocm-smi` provides power, temps, and memory usage. |
| **Compiler** | `nvcc` | `hipcc` | `hipcc` is the C++ compiler for HIP code. |
| **Profiler** | `nsys` / `nvprof` | `rocprof` | Use `rocprof` for tracing HIP API calls and kernels. |
| **Matrix Math** | `cuBLAS` | `rocBLAS` | Basic Linear Algebra Subprograms. |
| **Deep Learning** | `cuDNN` | `MIOpen` | Convolutions, activations, and primitives. |
| **Collectives** | `NCCL` | `RCCL` | Multi-GPU communication. |
| **Fast Fourier** | `cuFFT` | `rocFFT` | FFT operations. |
| **Random Gen** | `cuRAND` | `rocRAND` | Random number generation. |
| **Architecture ID**| `sm_80`, `sm_90` | `gfx90a`, `gfx942` | e.g., `gfx90a` = MI200, `gfx942` = MI300X. |

---

### Environment & Monitoring

When working at the bare-metal or container level, your muscle memory will need a slight adjustment:

*   **GPU Status:** Replace `watch -n 1 nvidia-smi` with `watch -n 1 rocm-smi`. For more detailed topology (equivalent to `nvidia-smi topo -m`), use `rocm-smi --showtopo`.
*   **Compilation:** When building C++ extensions, `nvcc` is replaced by `hipcc`. HIP (Heterogeneous-Compute Interface for Portability) is a C++ dialect designed to compile into both ROCm and CUDA, depending on the backend you target.
*   **Device Visibility:** If you want to mask GPUs from your script, `CUDA_VISIBLE_DEVICES=0,1` becomes `HIP_VISIBLE_DEVICES=0,1` (though PyTorch ROCm builds often respect the CUDA variable for backward compatibility, it's safer to use the HIP native variable).

---

### PyTorch & JAX Code Translation: The "Magic" of Device Mapping

The most pleasant surprise for developers migrating to ROCm is how little Python code actually needs to change.

*   **The `.to("cuda")` Illusion:** PyTorch developers explicitly preserve API compatibility. **Do not change your `.to("cuda")` calls.** Under the hood, the PyTorch ROCm build aliases the `cuda` device to the HIP backend. Calling `model.to("cuda")` or `x.cuda()` will seamlessly route your tensors to the AMD GPU. 
*   **JAX Compatibility:** Similarly, JAX abstracts the hardware. Once you install JAX with the ROCm plugin (`pip install jax[rocm] -f https://repo.radeon.com/rocm/manylinux/rocm-rel-X.Y/`), `jax.devices()` will recognize the AMD GPUs, and `jax.numpy` operations run natively without code changes.
*   **When Explicit Variables are Required:** You only need to touch explicit HIP variables when dealing with memory allocation or compiling custom C++ extensions. For instance, configuring the memory allocator might require `PYTORCH_HIP_ALLOC_CONF` instead of `PYTORCH_CUDA_ALLOC_CONF`.

---

### The Library Ecosystem: Direct Replacements

If your workload relies on optimized third-party libraries, you must swap dependencies.

1.  **Quantization (bitsandbytes → optimum-amd / AutoGPTQ):**
    *   *NVIDIA:* `bitsandbytes` is heavily optimized for CUDA PTX and handles 8-bit/4-bit quantization natively.
    *   *AMD:* Historically, compiling `bitsandbytes` on ROCm was a nightmare. Instead, migrate to Hugging Face's `optimum-amd`, or use `AutoGPTQ` / `AWQ`, which have native Triton/ROCm support for quantized inference.
2.  **Distributed Training (NCCL → RCCL):**
    *   *NVIDIA:* DistributedDataParallel (DDP) relies on `NCCL`.
    *   *AMD:* ROCm uses `RCCL`. Because RCCL implements the exact same API as NCCL, you **do not** need to change your PyTorch backend. `torch.distributed.init_process_group(backend="nccl")` will automatically invoke RCCL under the hood on an AMD machine.
3.  **Low-Level Math (cuBLAS/cuDNN → rocBLAS/MIOpen):**
    *   For 99% of PyTorch/JAX users, you don't interact with these directly. The pre-compiled binaries handle the routing. However, if you are writing custom kernels, you must link against `rocBLAS` instead of `cuBLAS`, and `MIOpen` instead of `cuDNN`.

---

### Porting Tools: HIPIFY Quick-Start

If you have custom custom `.cu` (CUDA) kernels, AMD provides the **HIPIFY** toolset to automate the translation to `.cpp` (HIP) kernels.

**1. `hipify-perl` (The Quick Regex Tool)**
Best for simple codebases. It uses text-based search-and-replace.
```bash
# Install
wget https://raw.githubusercontent.com/ROCm-Developer-Tools/HIPIFY/master/hipify-perl
chmod +x hipify-perl

# Convert
./hipify-perl my_cuda_kernel.cu > my_hip_kernel.cpp
```

**2. `hipify-clang` (The Robust AST Tool)**
Best for complex, macro-heavy C++ codebases. It parses the Abstract Syntax Tree (AST) using LLVM.
```bash
# Requires clang and ROCm dev tools installed
hipify-clang my_cuda_kernel.cu -- -I/usr/local/cuda/include

# This generates my_cuda_kernel.cu.hip containing the translated code.
```

---

### Common Pitfalls (The "Gotchas")

Avoid these three traps that catch out almost every migrating engineer:

**1. Docker Image Naming Conventions:**
Do not simply `pip install torch` on a base Linux image, and do not use `nvidia/cuda` base images. AMD's runtime relies heavily on kernel-level drivers. 
*   *Solution:* Always use the official ROCm PyTorch Docker images: `rocm/pytorch:latest` or pull explicitly from AMD's repository. Do not rely on standard `pytorch/pytorch` images, as they default to CUDA builds.

**2. Flash Attention Versioning:**
Standard `flash-attn` is heavily optimized around NVIDIA's Tensor Cores and PTX. Running `pip install flash-attn` on an AMD machine will fail during compilation.
*   *Solution:* You must use the ROCm fork of Flash Attention (e.g., `flash-attention-rocm` or via AMD's Composable Kernel library). Alternatively, simply use PyTorch 2.0+'s native `torch.nn.functional.scaled_dot_product_attention` (SDPA), which automatically routes to an optimal ROCm kernel (like memory-efficient attention) without custom installations.

**3. The `gfx` Target Architecture:**
In the CUDA world, we compile for `sm_80` (A100) or `sm_90` (H100). In ROCm, you must compile for the exact `gfx` architecture, and omitting this will result in massive silent compilation times or runtime crashes.
*   *Solution:* Know your hardware. Set `export PYTORCH_ROCM_ARCH="gfx90a"` for MI200 series or `"gfx942"` for MI300 series before compiling any custom wheels or extensions.