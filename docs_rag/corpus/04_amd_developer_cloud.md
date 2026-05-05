# How to Get Started on the AMD Developer Cloud

The AMD Developer Cloud offers access to AMD Instinct MI300X GPUs in a cloud environment. With GitHub-based login, preconfigured ROCm software, and Docker setups, it supports inference, fine-tuning, and training workloads.

Built for developers, researchers, and open-source users, the AMD Developer Cloud provides flexible VM configuration options: build from a bare OS, use ROCm-ready images with preinstalled software, or launch directly into a JupyterLab environment.

For a typical user, getting started is as simple as choosing a GPU plan and software image, adding an SSH key, creating the VM, and connecting via SSH.

## Launching a Virtual Machine

### 1. Choose a GPU plan

After logging in, choose whether you need a full MI300X node (8 GPUs) or a single MI300X GPU. An 8x MI300X VM consumes GPU-hours 8x faster. One hour on 8 GPUs counts as 8 GPU-hours.

### 2. Choose an image

Select an image that matches your preferred setup.

#### 2.1 Bare OS

Choose a minimal image with only the OS (various Ubuntu versions). This gives full control to install any ROCm version and custom libraries.

#### 2.2 Quick Start (ROCm-ready images)

Quick Start images include the latest publicly available ROCm version preinstalled. You can still install your preferred ROCm version later, even on a Quick Start image.

Within ROCm-ready images, you have two options:

- **Vanilla ROCm**: ROCm only, no extra AI/ML packages. Suitable for custom stack setup.
- **Quick Start Packages**: ROCm plus Docker images with preinstalled ML/LLM frameworks such as vLLM, SGLang, PyTorch, Megatron, and JAX.

Once connected via SSH, you can access the Docker container with:

```bash
docker exec -it rocm bash
```

This puts you directly into a container with the selected package ready to use.

### 3. Add an SSH key and create a VM

Add an SSH key via the UI. After clicking "Create GPU Droplet," you are redirected to your VM overview page.

### 4. Accessing a VM

After creation, the overview page shows your VM's public IP address. The "Quick Start" link under "Getting Started" provides detailed instructions. Below are the main access methods.

#### 4.1 SSH

Connect via SSH:

```bash
ssh root@<Public-IP-Address>
```

Example:

```bash
ssh root@134.199.194.177
```

After connecting, you will see startup info for the selected image. The terminal output includes instructions for accessing Jupyter Server and entering the Docker container.

#### 4.2 Web Console

The Web Console provides browser-based access. Click "Web Console" on the VM overview page to open a terminal session in a new window.

#### 4.3 JupyterLab

Quick Start images launch a Jupyter server automatically. Access JupyterLab by visiting your VM's public IP address in a browser and entering the unique token shown on the VM terminal (via SSH or Web Console).

Note:

- For Quick Start packages such as vLLM, Megatron, JAX, PyTorch, and SGLang, Jupyter runs inside the Docker container.
- For Vanilla ROCm, Jupyter runs on the base OS (no container preinstalled).

## Ready-to-use Jupyter notebook examples

Quick Start package images include example notebooks that are regularly updated. The vLLM Quick Start image, for example, includes notebooks such as an AI agent built with vLLM, Pydantic AI, and MCP to find Airbnb listings.

### vLLM notebook example: AI agent with MCPs using vLLM and Pydantic AI

1. Open the notebook and launch a vLLM server

Select `build_airbnb_agent.ipynb` in JupyterLab. Open a new terminal tab, then copy and run the vLLM serve command from Step 1 in the notebook. After the model loads, the server is ready to accept traffic through an OpenAI-compatible endpoint.

2. Run notebook cells and build your AI agent

Execute cells with Shift + Enter or the Run button, and follow the remaining steps at your own pace.

## Get started

AMD offers an initial 25 hours of complimentary cloud credit to qualified developers. To apply, create an account, open the GPU Droplet page, and submit the credit request form. When credits are granted, the droplet page shows a "credits applicable" message. If you run out, you can request more by submitting the form again.

### Taking advantage of complimentary credit

- Credits are valid for 10 days from approval.
- If credits are exhausted, access to the GPU and data is lost.
- Credits apply only to MI300X GPUs, not storage or backups.
- Powering off a VM still incurs charges for reserved resources.
- To maximize free credits, destroy the VM when done.
- To pause work, create a snapshot and later create a new VM from it. See [DigitalOcean snapshot pricing](https://docs.digitalocean.com/products/snapshots/details/pricing/#:~:text=Snapshots%20are%20charged%20at%20%240.06,the%20size%20of%20the%20snapshot.) for details.

## Conclusion

This guide covered the core steps to get started on the AMD Developer Cloud: choosing a VM image, creating a VM, accessing it via SSH/Web Console/JupyterLab, and using Quick Start images with preconfigured AI/ML frameworks. The platform supports building AI agents, fine-tuning, and inference at scale using AMD Instinct MI300X GPUs.
