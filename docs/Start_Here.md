# Start Here: SeaVision for New Users

This guide is for first-time users who are not computer vision specialists.

SeaVision helps you:

1. Run a detector on marine video.
2. Review and correct detections in the GUI.
3. Export validated detections for model training.
4. Optionally deploy trained models to edge devices.

## Before you begin

You need:

1. A suitable Python environmeant
2. Video files stored either: (i) on a hard drive; (ii) on your workstation; or 
    (iii) in an S3 bucket which you can access with an AWS SSO profile.

## Creating a python environment

The simplest way to create a suitable environment in most situations is to use
`conda`, an enviornment and package manager for python. If you do not use conda,
see [here](https://www.anaconda.com/) for more information.

Assuming you have a working conda installation you can ccreate an environment
for SeaVision as follows:

```bash
conda create -n seavision python=3.11
conda activate seavision
python -m pip install --upgrade pip
```

If you would prefer not to use conda you can use a virtual environment.

On Windows (in a PowerShell terminal):
```bash
py -3.11 -m venv .venv-seavision
.\.venv-seavision\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

On Linux:
```bash
python3.11 -m venv .venv-seavision
source .venv-seavision/bin/activate1
python -m pip install --upgrade pip
```

## Installing SeaVision

You can now install SeaVision into the environment you created using `pip`.

Assuming that you:
1. Want to run SeaVision detectors
2. Want to use the GUI for validation
3. Do not need to prepare a detection model for edge deployment

You can install SeaVision by running the following:

```bash
python -m pip install "seavision-python[gui]"
```

You can verify the installation by running the following commands and checking
that you don't get an error and that the GUI window launches:

```bash
seavision --help
seavision-gui
```


## The detection pipeline

Your first port of call after installing SeaVision will likely be to run the
detection pipeline. This will generate detection files that you can then review
in the GUI.

There are two main mechanisms for running SeaVision detection:
1. From the command line using the `seavision` command.
2. Programatically using the python API.

### CLI (best for novices)

For novice users, the CLI route is the simplest and requires less coding. The
CLI method uses YAML configuration files to inform the detection pipeline
orchestration.

Start by creating a local copy of the default configuration file:

```bash
seavision --write-default-config "path/to/write/config.yml"
```

Open the configuration file, either in a text editor such as Notepad or in a
coding IDE such as VS Code or PyCharm., then save a copy of the file which you
will modify.

Go through the file and adjust all the arguments to fit your scenario (file paths,
detection mode, output paths, confidence thresholds etc.)

For more information on each detector see the specific help page:
- [SAM3]() TODO: SAM3 detector help page
- [Community Fish Detector]() TODO: CFD detector help page - detector needs implementing
- [Motion]() TODO: Motion detection help page
- [YOLO]() TODO: YOLO detection help page
- [PyTorch]() TODO: PyTorch detection help page (detecotr needs implementing - test on shartrack)

Once you are happy with the configuration file, you can run detection as follows:

```bash
seavision --config "path/to/modified_config.yml"
```

There are multiple command line arguments which you can use to override config
settings for specific run scenarios. You can see these by running:

```bash
seavision --help
```

### Python API (best for advanced users or complex scenarios)

The CLI uses a specific orhestraion of the SeaVision detection pipeline which
may not be suitable in all scenarios. Some users may want greater control
over the way detection is run, the way outputs are saved, or the visualisation
of outputs.

In these cases users may prefer to use the python API provided by SeaVision.

TODO: Brief intro with links to more detailed documentation on the Python API.

## The GUI

After you have run the detection pipeline on your data, you will likley want to
visualise and review the detections it produced. You can do so using the
SeaVision GUI.

Launch the GUI:

```bash
seavision-gui
```

You can now use its functionality to review your detections, modify/correct them
or manually draw new detections on plain footage. For detailed help pages on
using the GUI see [here](.docs/gui/README.md)


## AWS S3 access

If yur footage is stored in an S3 bucket you can use SeaVision to access it
directly, stream frames and create detections on your local machine. This avoids
the need to download a local copy of the footage, or deploy the detection model
to the cloud.

In order to access S3-hosted footage with SeaVision you must 
[set up an AWS SSO access profile](.docs/AWS_SETUP.md) on your machine.

You can then specify `"s3"` as the video source, either programmatically via the
API, or with the YAML config file. The GUI also supports direct access to
S3-hosted footage/detections via the 'S3 Session' tools.
