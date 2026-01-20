# SeaVision

## Human-in-the-loop Computer Vision for Marine Environments

SeaVision provides an integrated frameowork for various Computer Vision
approaches to analyse marine monitoring data.

## Installation

### Prerequisites

- Python 3.10
- Conda (reccomemnded) or pip

### Setup

You can run the code in this repository by cloning the repository and installing
neccersary depedencies a follows with conda (reccomended) or pip:

```bash
# Clone Git repository
git clone github.com/mariolambrette/SeaVision
cd SeaVision

# Conda setup
conda env create -f environment.yml
conda activate seavision

# Pip setup
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

### AWS S3 Access (Optional)

The pipeline supports streaming video directly from AWS. In order to access this
feature you will need to configure an AWS SSO profile. For more information on
how to do this and integrate AWS streaming into the SeaVIsion workflow see the
[AWS setup documentation](./docs/AWS_SETUP.md)

## Quick start

To initially run the detection pipeline using the default configuration you can
run the following:

```bash
# Local files
python run_pipeline.py --input ./data/footage/ --output ./results/

# With config file
python run_pipeline.py --config config/default.yaml
```

## Configuration

The SeaVision pipeline can be fully cosutomised using YAML config files. For
a documented example of a config file see the
[default configuration](./config/default.yaml)

## Project Status

Note that this project is under [active development](./Bouy%20detection%20plan.md)
