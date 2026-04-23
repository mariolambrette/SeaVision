# SeaVision

<p align="center">
  <img src="https://raw.githubusercontent.com/mario_lambrette/SeaVision/main/assets/seavision_logo.png" alt="Logo" width="200"/>
</p>

## Human-in-the-loop Computer Vision for Marine Environments

SeaVision offers a practical computer vision workflow for marine monitoring. It supports the development of accurate, 
custom detection models for specific deployment scenarios. The main workflow is:

1. Deploy a generic detector (e.g. motion detection, SAM3-based semantic detection, etc.) on recorded footage.
2. Use the provided GUI to validate and refine detections into a training dataset.
3. Train a custom YOLO detection model.
4. Deploy the trained model on a desktop workstation or edge device with the provided export functionality.

If you are new to the project, start with the [Start Here guide](./docs/Start_Here.md).

## Start Here (New Users)

If you are not a computer vision specialist, use this short path first:

1. Read the [Start Here guide](./docs/Start_Here.md) for a plain-language workflow and glossary.
2. Install SeaVision in GUI mode: `python -m pip install ".[gui]"`.
3. Run `seavision-gui` and create a new session with `Ctrl+N`.
4. Follow the GUI [Getting Started guide](./docs/gui/Getting%20started.md).

## Installation

### Prerequisites

- Python 3.10+
- pip

### Install from a cloned repository

Before installing the package, you must currently clone this repository. Run the following in a
bash terminal:

```bash
git clone https://github.com/mariolambrette/SeaVision
cd SeaVision
```

It is recommended to install SeaVision in a dedicated environment. If you are a [conda](https://www.anaconda.com/docs/getting-started/anaconda/install/overview) user, run
the following:

```bash
conda create seavision
conda activate seavision
```

You can now install SeaVision using pip:

```bash
python -m pip install ".[<extras>]"
```

SeaVision can be installed in various modes, each of which supports different modes of functionality. See below for a full 
description of all installation modes.

### Install Matrix (User Types)

Use the install command that matches your use case.

| User type | Install command | Primary CLI command(s) |
|---|---|---|
| Detection-only users (local videos) | `python -m pip install .` | `seavision` |
| Detection users with videos in S3 bucket | `python -m pip install ".[s3]"` | `seavision` |
| GUI users (includes S3 support) | `python -m pip install ".[gui]"` | `seavision-gui` |
| Edge device operators (runtime only) | `python -m pip install ".[edge]"` | `seavision-edge` |
| Export users (prepare edge artifacts) | `python -m pip install ".[export]"` | `seavision-export` |
| Advanced/full users | `python -m pip install ".[all]"` | `seavision`, `seavision-gui`, `seavision-export`, `seavision-edge` |

Most users should use either `python -m pip install ".[gui]"` for desktop-only usage or `python -m pip install ".[all]"` if they are
also likely to use edge deployment functionality. Other installation methods may provide lighter dependencies in specific scenarios.

You can verify your installation by running [test commands](#install-verification)

### Development install

```bash
python -m venv venv
venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
```

For release/distribution policy and compatibility targets, see:

- [Distribution and compatibility policy](./docs/release/Distribution_and_Compatibility.md)

### Optional GPU acceleration

The above install allows you to run all SeaVision functionality but does not
provide support for GPU-accelerated processing. Some methods (e.g. SAM3-based
detection) will be significantly faster if a GPU is available. You will need to
install GPU-specific dependencies manually based on your hardware.

For example, to run on an NVIDIA RTX 5090 GPU with cuda 13 you could install
the following:

```bash
pip install torch>=2.9.0 torchvision>=0.20.0 --index-url https://download.pytorch.org/whl/cu130 --force-reinstall
```
You can find more information on PyTorch compatibility
[here](https://pytorch.org/get-started/locally/).

### AWS S3 Access (Optional)

The pipeline supports streaming video directly from AWS. In order to access this
feature you will need to configure an AWS SSO profile. For more information on
how to do this and integrate AWS streaming into the SeaVision workflow, see the
[AWS setup documentation](./docs/AWS_SETUP.md)

## Install verification

Run the command that matches your installed mode:

```bash
# Detection CLI
seavision --help

# GUI
seavision-gui

# Export CLI
seavision-export --help

# Edge CLI
seavision-edge --help
```

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

### 2. Launch the GUI

```bash
seavision-gui
```

### 3. Export for edge deployment

```bash
seavision-export --weights models/fish.pt --output ./deployment --target onnx
```

### 4. Run on an edge device

```bash
seavision-edge --artifact-dir ./deployment/artifact
```

## Troubleshooting quick checks

| Problem | Likely cause | Quick check | Fix |
|---|---|---|---|
| `seavision: command not found` | Package not installed in active environment | `python -m pip show seavision` | Activate the right environment and reinstall using the install matrix |
| `seavision-gui: command not found` | GUI extra not installed | `python -m pip show PySide6` | `python -m pip install ".[gui]"` |
| `seavision-edge: command not found` | Edge extra not installed | `python -m pip show onnxruntime` | `python -m pip install ".[edge]"` |
| Import error for `boto3` when using S3 | S3 dependency missing | `python -m pip show boto3` | `python -m pip install ".[s3]"` or `python -m pip install ".[gui]"` |
| GUI starts but S3 login fails | AWS credentials/session not configured | `aws sts get-caller-identity` | Run `aws sso login --profile <profile-name>` and retry |
| Edge run fails at startup validation | Artifact dir incomplete or invalid | `seavision-edge --artifact-dir <path>` output | Re-run `seavision-export` and copy the full artifact directory again |

## Configuration

The SeaVision pipeline can be fully customised using YAML config files. For
a documented example of a config file see the
[default configuration](./config/default.yaml)


## Edge Deployment

Users may wish to deploy models developed or refined using SeaVision to an edge
device. Full support is provided for deploying trained model weight files
(`*.pt`) on Raspberry Pi.

Edge deployment uses a locally installed wheel runtime plus an exported model
artifact. Briefly the process involves:

1. Export the `*.pt` file on the workstation with `seavision-export`
2. Copy the created artifact to the Pi.
3. Install the SeaVision edge wheel on the Pi.
4. Launch the runtime against the artifact.

Edge deployment creates SeaVision detection files directly on the Pi which may
save compute time, power and data transfer requirements. Users can optionally
export periodic validation clips alongside the detections. See below for 
detailed documentation:

- [Edge deployment overview](./docs/edge/README.md)
- [Operator quickstart](./docs/edge/Operator%20Quickstart.md)
- [Wheel runtime workflow](./docs/edge/Wheel%20Runtime.md)
- [Model artifact layout](./docs/edge/Model%20Artifacts.md)
- [Deploy to Raspberry Pi](./docs/edge/Deploy%20to%20Raspberry%20Pi.md)
- [Rollback runbook](./docs/edge/Rollback%20Runbook.md)

## Documentation

- [Start Here guide](./docs/Start_Here.md)
- [Class and API reference](./docs/Class_reference.md)
- [Architecture and class diagrams](./docs/Class_diagram.md)
- [AWS setup guide](./docs/AWS_SETUP.md)
- [Edge deployment docs](./docs/edge/README.md)
- [GUI docs](./docs/gui/README.md)

## Project Status

Note that this project is under active development and features may not yet
work as intended.
