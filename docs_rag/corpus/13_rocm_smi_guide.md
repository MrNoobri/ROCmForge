# rocm-smi Guide — AMD GPU Monitoring

`rocm-smi` is the AMD equivalent of `nvidia-smi`. It reports GPU status, memory usage, temperature, utilization, and process information for AMD Instinct GPUs.

## Common Command Equivalents

| Task | NVIDIA | AMD |
|---|---|---|
| GPU overview | `nvidia-smi` | `rocm-smi` |
| Watch live (1s refresh) | `watch -n 1 nvidia-smi` | `watch -n 1 rocm-smi` |
| Memory usage | `nvidia-smi --query-gpu=memory.used,memory.free --format=csv` | `rocm-smi --showmeminfo vram` |
| GPU utilization | `nvidia-smi --query-gpu=utilization.gpu --format=csv` | `rocm-smi --showuse` |
| Temperature | `nvidia-smi --query-gpu=temperature.gpu --format=csv` | `rocm-smi --showtemp` |
| Running processes | `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` | `rocm-smi --showpids` |
| GPU topology | `nvidia-smi topo -m` | `rocm-smi --showtopo` |
| Power draw | `nvidia-smi --query-gpu=power.draw --format=csv` | `rocm-smi --showpower` |
| Fan speed | `nvidia-smi --query-gpu=fan.speed --format=csv` | `rocm-smi --showfan` |

## JSON Output (Used by benchmark_runner.py)

`rocm-smi` supports JSON output for programmatic parsing:

```bash
rocm-smi --showmeminfo vram --json
```

Example output:

```json
{
    "card0": {
        "VRAM Total Memory (B)": "137438953472",
        "VRAM Total Used Memory (B)": "4294967296"
    }
}
```

Parsing in Python:

```python
import subprocess, json

result = subprocess.run(
    ["rocm-smi", "--showmeminfo", "vram", "--json"],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
used_bytes = int(data["card0"]["VRAM Total Used Memory (B)"])
used_gb = used_bytes / (1024 ** 3)
```

## Checking GPU Architecture

Before compiling custom kernels or choosing a Docker image, identify your GPU's gfx architecture:

```bash
rocminfo | grep gfx
```

Common results:

| Architecture | GPU |
|---|---|
| `gfx90a` | AMD Instinct MI200 series (MI210, MI250, MI250X) |
| `gfx942` | AMD Instinct MI300 series (MI300X, MI300A) |
| `gfx1100` | Radeon RX 7900 series (consumer GPU) |

Use this value when setting:

```bash
export PYTORCH_ROCM_ARCH="gfx942"   # before building custom extensions
export HIP_VISIBLE_DEVICES=0         # restrict to GPU 0 (equivalent of CUDA_VISIBLE_DEVICES)
```

## GPU Visibility Environment Variables

```bash
# NVIDIA
export CUDA_VISIBLE_DEVICES=0,1

# AMD (preferred)
export HIP_VISIBLE_DEVICES=0,1

# Note: PyTorch ROCm builds also respect CUDA_VISIBLE_DEVICES for backwards compatibility,
# but HIP_VISIBLE_DEVICES is the authoritative variable on AMD systems.
```

## Checking Memory Before/After a Run

Useful pattern for benchmarking scripts:

```bash
# Before
rocm-smi --showmeminfo vram --json > before.json

# Run your script
python3 app.py

# After
rocm-smi --showmeminfo vram --json > after.json
```

Or inline in Python using subprocess, capturing the delta to report GPU memory used by a workload.

## rocm-smi in a Docker Container

`rocm-smi` works inside a Docker container as long as the container was started with the required device flags:

```bash
docker run --device=/dev/kfd --device=/dev/dri --group-add video rocm/pytorch:latest rocm-smi
```

Without `--device=/dev/kfd` and `--device=/dev/dri`, `rocm-smi` will report no GPUs found.
