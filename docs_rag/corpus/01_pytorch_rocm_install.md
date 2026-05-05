# PyTorch on ROCm installation

PyTorch is an open-source tensor library designed for deep learning. PyTorch on ROCm provides mixed-precision and large-scale training using AMD MIOpen and RCCL libraries.

This topic covers setup instructions and the necessary files to build, test, and run PyTorch with ROCm support in a Docker environment. To learn more about PyTorch on ROCm, including its use cases, recommendations, and hardware/software compatibility, see the PyTorch compatibility page.

## Install PyTorch

To install PyTorch for ROCm, you have the following options:

- Use a prebuilt Docker image with PyTorch pre-installed (recommended)
- Use a wheels package
- Use the PyTorch upstream Dockerfile

### Use a prebuilt Docker image with PyTorch pre-installed

The recommended setup to get a PyTorch environment is through Docker, as it avoids potential installation issues. The tested, prebuilt image includes PyTorch, ROCm, and other dependencies.

1. Download the latest public PyTorch Docker image:

```bash
docker pull rocm/pytorch:latest
```

Important: the `rocm/pytorch:latest` tag points to a Docker image with the latest ROCm-tested release of PyTorch.

You can download Docker images with specific ROCm, PyTorch, and operating system versions. See the available tags on Docker Hub.

2. Start a Docker container using the image:

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

Note: This automatically downloads the image if it does not exist on the host. You can also pass `-v` to mount any data directories from the host onto the container.

### Docker image support

AMD validates and publishes ready-made PyTorch images with ROCm backends on Docker Hub. The following Docker image tags and associated inventories are validated for ROCm 7.2.2.

#### PyTorch 2.9.1

**Python 3.12**

Docker pull tag:

```bash
docker pull rocm/pytorch:rocm7.2.2_ubuntu24.04_py3.12_pytorch_release_2.9.1
```

Additional software components:

- Ubuntu: 24.04
- Apex: 1.9.0+rocm7.2.2
- torchvision: 0.24.0
- UCX: 1.16.0+ds-5ubuntu1
- Open MPI: 4.1.6-7ubuntu2

**Python 3.10**

Docker pull tag:

```bash
docker pull rocm/pytorch:rocm7.2.2_ubuntu22.04_py3.10_pytorch_release_2.9.1
```

Additional software components:

- Ubuntu: 22.04
- Apex: 1.9.0+rocm7.2.2
- torchvision: 0.24.0
- UCX: 1.12.1~rc2-1
- Open MPI: 4.1.2-2ubuntu1

#### PyTorch 2.8.0

**Python 3.12**

Docker pull tag:

```bash
docker pull rocm/pytorch:rocm7.2.2_ubuntu24.04_py3.12_pytorch_release_2.8.0
```

Additional software components:

- Ubuntu: 24.04
- Apex: 1.8.0+rocm7.2.2
- torchvision: 0.23.0
- UCX: 1.16.0+ds-5ubuntu1
- Open MPI: 4.1.6-7ubuntu2

**Python 3.10**

Docker pull tag:

```bash
docker pull rocm/pytorch:rocm7.2.2_ubuntu22.04_py3.10_pytorch_release_2.8.0
```

Additional software components:

- Ubuntu: 22.04
- Apex: 1.8.0+rocm7.2.2
- torchvision: 0.23.0
- UCX: 1.12.1~rc2-1
- Open MPI: 4.1.2-2ubuntu1

#### PyTorch 2.7.1

**Python 3.12**

Docker pull tag:

```bash
docker pull rocm/pytorch:rocm7.2.2_ubuntu24.04_py3.12_pytorch_release_2.7.1
```

Additional software components:

- Ubuntu: 24.04
- Apex: 1.7.0+rocm7.2.2
- torchvision: 0.22.1
- UCX: 1.16.0+ds-5ubuntu1
- Open MPI: 4.1.6-7ubuntu2

**Python 3.10**

Docker pull tag:

```bash
docker pull rocm/pytorch:rocm7.2.2_ubuntu22.04_py3.10_pytorch_release_2.7.1
```

Additional software components:

- Ubuntu: 22.04
- Apex: 1.7.0+rocm7.2.2
- torchvision: 0.22.1
- UCX: 1.12.1~rc2-1
- Open MPI: 4.1.2-2ubuntu1

### Use a wheels package

PyTorch supports the ROCm platform by providing tested wheels packages. To access this feature, go to pytorch.org/get-started/locally/. For the correct wheels command, you must select Linux, Python, pip, and ROCm in the matrix.

Note: The available ROCm release varies between the PyTorch build of Stable or Nightly. More recent releases are generally available through the Nightly builds.

#### Setting up the environment for the wheel installation

1. Choose one of the following options:

**Option 1**

a. Download a base Docker image with the correct ROCm version:

- Ubuntu 22.04: `rocm/dev-ubuntu-22.04`
- Ubuntu 24.04: `rocm/dev-ubuntu-24.04`

b. Pull the selected image:

```bash
docker pull rocm/dev-ubuntu-22.04:latest
```

c. Start a Docker container using the downloaded image:

```bash
docker run -it --device=/dev/kfd --device=/dev/dri --group-add video rocm/dev-ubuntu-22.04:latest
```

**Option 2**

a. Select a base OS Docker image. Check system requirements for Linux.

b. Pull selected base OS image (Ubuntu 22.04, for example):

```bash
docker pull ubuntu:22.04
```

c. Start a Docker container using the downloaded image:

```bash
docker run -it --device=/dev/kfd --device=/dev/dri --group-add video ubuntu:22.04
```

d. Install ROCm using the directions in the ROCm installation overview section.

**Option 3**

Install on bare metal. Check system requirements for Linux and install ROCm using the instructions in the ROCm installation overview section.

2. Install the required dependencies for the wheels package:

```bash
sudo apt update
sudo apt install libjpeg-dev python3-dev python3-pip
pip3 install wheel setuptools
```

3. Install `torch`, `torchvision`, and `torchaudio`, as specified in the installation matrix:

```bash
pip3 install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/rocm7.2
```

Note: The above command uses the ROCm 7.2 PyTorch wheel. If you want a different version of ROCm, modify the command accordingly.

### Build PyTorch from source

Use the `rocm/pytorch:latest` image, uninstall the preinstalled PyTorch package, and rebuild PyTorch from source. This ensures compatibility with your specific ROCm version, GPU architecture, and project requirements.

1. Download the latest PyTorch Docker image:

```bash
docker pull rocm/pytorch:latest
```

2. Start a Docker container using the downloaded image:

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

3. Uninstall the pre-installed PyTorch inside the container:

```bash
pip3 uninstall -y torch torchvision torchaudio
```

4. Clone the PyTorch repository:

```bash
cd ~
git clone https://github.com/pytorch/pytorch.git
cd pytorch
git submodule update --init --recursive
```

5. (Optional) Set your ROCm architecture to speed up compilation:

```bash
rocminfo | grep gfx
export PYTORCH_ROCM_ARCH=<uarch>
```

Replace `<uarch>` with the result from `rocminfo` (for example, `gfx90a`, `gfx1030`). See system requirements for the list of AMD GPU architectures.

6. Build and install PyTorch following the instructions in the PyTorch repository README.

### Use the PyTorch upstream Dockerfile

If you do not want to use a prebuilt base Docker image, you can build a custom base Docker image using scripts from the PyTorch repository. This uses a standard Docker image from operating system maintainers and installs all the required dependencies, including ROCm, torchvision, conda packages, and the compiler toolchain.

1. Clone the PyTorch repository:

```bash
cd ~
git clone https://github.com/pytorch/pytorch.git
cd pytorch
git submodule update --init --recursive
```

2. Build the PyTorch Docker image:

```bash
cd .ci/docker
./build.sh pytorch-linux-<os-version>-rocm<rocm-version>-py<python-version> -t rocm/pytorch:build_from_dockerfile
```

Where:

- `<os-version>` = `ubuntu20.04` (or `focal`), `ubuntu22.04` (or `jammy`)
- `<rocm-version>` = `6.0`, `6.1`, `6.2`
- `<python-version>` = `3.8` - `3.11`

To verify that your image was successfully created, run:

```bash
docker image ls rocm/pytorch:build_from_dockerfile
```

If successful, the output looks like this:

```text
REPOSITORY    TAG                       IMAGE ID         CREATED           SIZE
rocm/pytorch  build_from_dockerfile     17071499be47     2 minutes ago     32.8GB
```

3. Start a Docker container using the image with the mounted PyTorch folder:

```bash
docker run -it --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
--user root --device=/dev/kfd --device=/dev/dri \
--group-add video --ipc=host --shm-size 8G \
-v ~/pytorch:/pytorch rocm/pytorch:build_from_dockerfile
```

You can also pass `-v` to mount any data directories from the host onto the container.

4. Go to the PyTorch directory:

```bash
cd /pytorch
```

5. Set ROCm architecture:

```bash
rocminfo | grep gfx
export PYTORCH_ROCM_ARCH=<uarch>
```

Where `<uarch>` is the architecture reported by `rocminfo`.

6. Build PyTorch:

```bash
.ci/pytorch/build.sh
```

This converts PyTorch CUDA sources to HIP and builds the PyTorch framework.

To check if your build is successful:

```bash
echo $?  # should return 0 if success
```

## Test the PyTorch installation

You can use PyTorch unit tests to validate your PyTorch installation. If you used a prebuilt PyTorch Docker image from AMD ROCm Docker Hub or installed an official wheels package, validation tests are not necessary.

If you want to manually run unit tests to validate your PyTorch installation fully, follow these steps:

1. Import the `torch` package in Python to test if PyTorch is installed and accessible.

Note: Do not run the following command from the PyTorch home directory.

```bash
python3 -c 'import torch' 2> /dev/null && echo 'Success' || echo 'Failure'
```

2. Check if the GPU is accessible from PyTorch:

```bash
python3 -c 'import torch; print(torch.cuda.is_available())'
```

3. Run unit tests to validate the PyTorch installation fully.

Note: You must run the following command from the PyTorch home directory.

```bash
PYTORCH_TEST_WITH_ROCM=1 python3 test/run_test.py --verbose \
--include test_nn test_torch test_cuda test_ops \
test_unary_ufuncs test_binary_ufuncs test_autograd
```

This command ensures that the required environment variable is set to skip certain unit tests for ROCm. This also applies to wheel installs in a non-controlled environment.

Note: Make sure your PyTorch source code corresponds to the PyTorch wheel or the installation in the Docker image. Incompatible PyTorch source code can give errors when running unit tests.

Some tests may be skipped, as appropriate, based on your system configuration. ROCm does not support all PyTorch features; tests that evaluate unsupported features are skipped. Other tests might be skipped, depending on host or GPU memory and the number of available GPUs.

If the compilation and installation are correct, all tests will pass.

4. (Optional) Run individual unit tests:

```bash
PYTORCH_TEST_WITH_ROCM=1 python3 test/test_nn.py --verbose
```

You can replace `test_nn.py` with any other test set.

## Run a PyTorch example

The PyTorch examples repository provides basic examples that exercise the functionality of your framework.

Two of our favorite testing databases are:

- MNIST: A database of handwritten digits that can be used to train a convolutional neural network for handwriting recognition.
- ImageNet: A database of images that can be used to train a network for visual object recognition.

### MNIST PyTorch example

1. Clone the PyTorch examples repository:

```bash
git clone https://github.com/pytorch/examples.git
```

2. Go to the MNIST example folder:

```bash
cd examples/mnist
```

3. Follow the instructions in the `README.md` file in this folder to install the requirements. Then run:

```bash
python3 main.py
```

This generates the following output:

```text
...
Train Epoch: 14 [58240/60000 (97%)]     Loss: 0.010128
Train Epoch: 14 [58880/60000 (98%)]     Loss: 0.001348
Train Epoch: 14 [59520/60000 (99%)]     Loss: 0.005261

Test set: Average loss: 0.0252, Accuracy: 9921/10000 (99%)
```

### ImageNet PyTorch example

1. Clone the PyTorch examples repository (if you did not already do this in the preceding MNIST example):

```bash
git clone https://github.com/pytorch/examples.git
```

2. Go to the ImageNet example folder:

```bash
cd examples/imagenet
```

3. Follow the instructions in the `README.md` file in this folder to install the requirements. Then run:

```bash
python3 main.py
```

## Troubleshooting

- **hipErrorNoBinaryForGPU: Unable to find code object for all current devices!**

The error denotes that the installation of PyTorch and/or other dependencies or libraries do not support the current GPU. To work around this issue, use the following steps:

1. Confirm that the hardware supports the ROCm stack. Refer to system requirements for Linux and system requirements for Windows.
2. Determine the gfx target:

```bash
rocminfo | grep gfx
```

3. Check if PyTorch is compiled with the correct gfx target:

```bash
TORCHDIR=$( dirname $( python3 -c 'import torch; print(torch.__file__)' ) )
llvm-readobj --offloading $TORCHDIR/lib/libtorch_hip.so  # check for gfx target
```

Note: Recompile PyTorch with the right gfx target if compiling from source and the hardware is not supported.

- **Unable to access Docker or GPU in user accounts**

Ensure that the user is added to docker, video, and render Linux groups as described in the GPU access permissions section.

- **Install PyTorch directly on bare metal**

Bare-metal installation of PyTorch is supported through wheels. For more information, see the wheels package section above.

- **Profile PyTorch workloads**

Use the PyTorch Profiler as described in the ROCm documentation to profile GPU kernels on ROCm.
