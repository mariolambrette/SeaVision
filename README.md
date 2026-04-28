<p align="left">
  <img src="https://raw.githubusercontent.com/mariolambrette/SeaVision/Main/assets/seavision_logo.jpg" alt="Logo" width="200"/>
</p>

# SeaVision

## Human-in-the-loop Computer Vision for Marine Environments

> [!WARNING]
> Documentation is currently out of date.
> The packaging, release, and edge-deployment flows have changed recently, and
> some instructions in this README and the linked docs may still describe older
> clone-first or pre-release workflows. Treat the published release artifacts
> and current CLI behavior as the source of truth until the docs are refreshed.

SeaVision offers a practical computer vision workflow for marine monitoring. It supports the development of accurate, 
custom detection models for specific deployment scenarios. A typical SeaVision
workflow involves:

1. Record marine monitoring footage
  * This footage can be recorded to a hard drive, stored directly on a 
    workstation or stored in an [S3 bucket](https://en.wikipedia.org/wiki/Amazon_S3)
    in the cloud.
2. Process the footage with a generalisable detector.
  * This first-pass processing uses a coarse, generalisable detector that
    returns candiate detections for manual review.
  * Currently implemented detectors include [SAM3](https://ai.meta.com/research/sam3/)-based semantic detection,
    motion detection, and the [Community Fish Detector](https://github.com/filippovarini/community-fish-detector)
3. Use the [SeaVision GUI](TODO: Link to GUI docs) to review the output of the
   generalisable detector.
   * The GUi is used for validation (i.e. how accurate is the generalisable
    detector on my footage?) and for generating training data.
4. Train a custom model using the GUI outputs
  * Annotations made in the GUI can be exported and [converted to YOLO format](TODO: docs for converting SeaVision detections o YOLO format).
  * These annotations can be used to train a custom YOLO detection model with
    the ultralytics framework. See [here](https://docs.ultralytics.com/modes/train/) for details.
  * Model training wihtin SeaVision is not currently supported as the ultralytics
    API abstracts most complexity already.
5. Deploy the trained detection model on recorded and furture footage.
  * The trained YOLO model can be deployed using the SeaVision frameowrk by using
    the YOLODetector class.
  * Users can deploy the model on a worstation, on the cloud or onto an edge
    device.

If you are new to the project, start with the [Start Here guide](./docs/Start_Here.md).

## Installation

### Prerequisites

- Python 3.10-3.12
- pip
- SeaVision is currently only tested on Windows and Linux systems. Installations
  on MacOS have not been thouroughly tested though may work in certain 
  circumstances

### Install with pip

SeaVision can be installed using pip in a suitable python environemnt.

#### Conda
For conda users:
```bash
conda create -n seavision python=3.11
conda activate seavision
python -m pip install --upgrade pip
```

#### Venv (Windows)
For windows users withough conda run the following in a powershell terminal:
```bash
py -3.11 -m venv .venv-seavision
.\.venv-seavision\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

#### Venv (Linux)
In Linux, without conda run the following:
```bash
python3.11 -m venv .venv-seavision
source .venv-seavision/bin/activate1
python -m pip install --upgrade pip
```

**NB: python version 3.10 and 3.12 will also work**

#### Install
You can now install SeaVision using pip on both Linux and Windows run:

```bash
python -m pip install "seavision-python[<extras>]"
```

SeaVision can be installed in various modes, each of which supports different modes of functionality. See below for a full 
description of all installation modes.

### Install Matrix (User Types)

Use the install command that matches your use case.

| User type | Install command | Primary CLI command(s) |
|---|---|---|
| Detection-only users (local videos) | `python -m pip install seavision-python` | `seavision` |
| Detection users with videos in S3 bucket | `python -m pip install "seavision-python[s3]"` | `seavision` |
| GUI users (includes S3 support) | `python -m pip install "seavision-python[gui]"` | `seavision-gui` |
| Edge device operators (runtime only) | `python -m pip install "seavision-python[edge]"` | `seavision-edge` |
| Export users (prepare edge artifacts) | `python -m pip install "seavision-python[export]"` | `seavision-export` |
| Advanced/full users | `python -m pip install "seavision-python[all]"` | `seavision`, `seavision-gui`, `seavision-export`, `seavision-edge` |

Most users should use either `python -m pip install ".[gui]"` for desktop-only 
usage or `python -m pip install ".[all]"` if they are also likely to use edge 
deployment functionality. Other installation methods may provide lighter
dependencies in specific scenarios. For example, a user only wanting to use the 
detection pipeline on a local machine may not need the S3 and GUI dependencies 
and would therefore prefer the standard installation with no extras.

### Optional GPU acceleration

The above install allows you to run all SeaVision functionality but does not
provide support for GPU-accelerated processing. Some methods (e.g. SAM3-based
detection) will be significantly faster if a GPU is available. You will need to
install GPU-specific dependencies manually based on your hardware.

For example, to run on an NVIDIA RTX 5090 GPU with cuda 13 you could install
the following:

```bash
python -m pip install torch>=2.9.0 torchvision>=0.20.0 --index-url https://download.pytorch.org/whl/cu130 --force-reinstall
```

You can find more information on PyTorch compatibility
[here](https://pytorch.org/get-started/locally/).

### S3 Bucket Access (Optional)

The pipeline supports streaming video directly from S3 buckets. In order to access this
feature you will need to configure an AWS SSO profile. For more information on
how to do this and integrate AWS streaming into the SeaVision workflow, see the
[AWS setup documentation](./docs/AWS_SETUP.md) # TODO: Verify the AWS set up docs

## Quick start

### 1. Run the detection pipeline

The full detection pipeline can be run with a CLI command, which can optionally be configured
with a [YAML file](./config/default.yaml)

```bash
# Local files
seavision --input ./data/footage/ --output ./results/

# With config file
seavision --config config/default.yaml
```

After installing SeaVision you can create a local copy of the config file by 
running the following in a terminal:

```bash
seavision --write-default-config "path/to/write/config.yml"
```

Each argument in the config file is explained within the file. Specific detector
class documentation can also be found within the source code and may provide
additional context.

### 2. Launch the GUI

You can launch the SeaVision GUI by running hte following in a terminal:

```bash
seavision-gui
```

Here, you can view, validate and manually modify detections created by the
SeaVision detection pipeline. See the [docs](TODO: GUI docs) for more info

### 3. Export for edge deployment

TODO: Need to verify these commands and update them.

```bash
seavision-export --weights models/fish.pt --output ./deployment --target onnx
```

### 4. Run on an edge device

```bash
seavision-edge --artifact-dir ./deployment/artifact
```

For full documentation of the edge deployment process see here:
1. [Edge deployment overview](./docs/edge/README.md)
2. [Concepts and Terms](./docs/edge/Concepts%20and%20Terms.md)
3. [Prerequisites Checklist](./docs/edge/Prerequisites%20Checklist.md)
4. [Operator Quickstart](./docs/edge/Operator%20Quickstart.md)
5. [Troubleshooting](./docs/edge/Troubleshooting.md)

## Troubleshooting quick checks

| Problem | Likely cause | Quick check | Fix |
|---|---|---|---|
| `seavision: command not found` | Package not installed in active environment | `python -m pip show seavision` | Activate the right environment and reinstall |
| `seavision-gui: command not found` | GUI extra not installed | `python -m pip show PySide6` | `python -m pip install "seavision-python[gui]"` |
| `seavision-edge: command not found` | Edge extra not installed | `python -m pip show onnxruntime` | `python -m pip install "seavision-python[edge]"` |
| Import error for `boto3` when using S3 | S3 dependency missing | `python -m pip show boto3` | `python -m pip install ".[s3]"` or `python -m pip install "seavision-python[gui]"` |
| GUI starts but S3 login fails | AWS credentials/session not configured | `aws sts get-caller-identity` | Run `aws sso login --profile <profile-name>` and retry |


## Documentation

- [Start Here guide](./docs/Start_Here.md)
- [Class and API reference](./docs/Class_reference.md) TODO: Reproduce class reference
- [Architecture and class diagrams](./docs/Class_diagram.md) # TODO: Reproduce class diagrams
- [AWS setup guide](./docs/AWS_SETUP.md) # TODO: Check this guide is up to date and user friendly
- [Edge deployment docs](./docs/edge/README.md)
- [GUI docs](./docs/gui/README.md) # ENsure the GUI docs are comprehensive and user firendly

## Project Status

Note that this project is under active development and features may not yet
work as intended.
