# Running SAM3 with SeaVision on AWS-hosted footage

This guide explains how to use [SeaVision](https://github.com/mariolambrette/SeaVision)
to run SAM3-based object detection on video footage stored in an AWS S3 bucket.
The workflow discovers video files under a specified S3 prefix, streams and processes
them locally, and writes detection results to CSV.

---

## Prerequisites

- Python 3.10+
- [conda](https://docs.conda.io/en/latest/) or another virtual environment manager
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed and on your `PATH`
- Read access to the target S3 bucket (via an AWS named profile or environment credentials)
- A [Hugging Face](https://huggingface.co) account with an access token (for SAM3 model weights)
- A machine with a CUDA-capable GPU is strongly recommended; CPU inference is possible but slow

---

## 1. Installation

### 1.1 Create a Python environment

```bash
conda create -n seavision python=3.12 -y
conda activate seavision
```

### 1.2 Install SeaVision

Clone the repository and install it in editable mode:

```bash
git clone https://github.com/mariolambrette/SeaVision
cd SeaVision
pip install -e .[all]
```

---

## 2. AWS access

You need AWS credentials that allow `s3:ListBucket` and `s3:GetObject` on the
target bucket.

### Option A — Named profile (recommended)

Configure a named profile with the AWS CLI. For SSO-backed accounts:

```bash
aws configure sso
```

Follow the prompts. The profile name you choose (e.g. `my-project`) is what you
will set as `AWS_PROFILE` below.

### Option B — Static credentials

```bash
aws configure --profile my-project
```

Enter your access key ID and secret access key when prompted.

### Verify access

```bash
aws s3 ls s3://<your-bucket>/ --profile my-project
```

---

## 3. Hugging Face token

SAM3 weights are hosted on Hugging Face. Generate a read-only access token from
your account settings (see the
[Hugging Face token docs](https://huggingface.co/docs/hub/en/security-tokens)) and
export it before running:

```bash
export HF_TOKEN="hf_..."
```

Or add it to your shell profile / `.env` file so it persists across sessions.

---

## 4. Configuration

All runtime settings are passed to the detection script as **environment
variables**. Set these before running — for example, by exporting them in your
shell or by writing a small wrapper script.

| Variable | Description | Example |
|---|---|---|
| `AWS_PROFILE` | Named AWS CLI profile for S3 access | `my-project` |
| `SAM3_S3_BUCKET` | S3 bucket name | `my-footage-bucket` |
| `DATA_PREFIX` | Path to the footage directory on the S3 bucket | `<directory_1>/<directory_2>/` |
| `SAM3_VIDEO_PATTERN` | Glob pattern for matching video files | `*.ts` |
| `SAM3_OUTPUT_DIRNAME_ROOT` | Root directory for detection CSV outputs (local) | `sam3_detections` |
| `SAM3_CHECKPOINT` | SAM3 model checkpoint (Hugging Face repo ID) | `facebook/sam3` |
| `SAM3_DEVICE` | PyTorch device string | `cuda` or `cpu` |
| `SAM3_IMGSZ` | Input image size for the detector | `644` |
| `SAM3_PROMPTS` | Comma-separated list of text prompts for detection | `chain,rope,debris,fish,seal` |
| `SAM3_KEEP_LABELS` | Comma-separated labels to retain after filtering | `fish,seal` |
| `SAM3_CONFIDENCE_THRESHOLD` | Minimum detection confidence score | `0.45` |
| `SAM3_IOU_SUPPRESSION_THRESHOLD` | IoU threshold for non-maximum suppression | `0.70` |
| `SAM3_MOTION_WINDOW_SECONDS` | Temporal window (s) used by the motion-track post-processor | `3.0` |
| `SAM3_MOTION_THRESHOLD_FRACTION` | Fraction of box size a detection must move to survive motion filtering | `0.4` |

### Example: setting configuration in a shell script

Create a file (e.g. `config.sh`) and source it before running:

```bash
#!/usr/bin/env bash

export AWS_PROFILE="my-project"
export SAM3_S3_BUCKET="my-footage-bucket"
export DATA_PREFIX="<directory_1>/<directory_2>/"
export SAM3_VIDEO_PATTERN="*.ts"

export SAM3_OUTPUT_DIRNAME_ROOT="sam3_detections"
export SAM3_CHECKPOINT="facebook/sam3"
export SAM3_DEVICE="cuda"
export SAM3_IMGSZ="644"

export SAM3_PROMPTS="chain,rope,debris,fish,seal"
export SAM3_KEEP_LABELS="fish,seal"
export SAM3_CONFIDENCE_THRESHOLD="0.45"
export SAM3_IOU_SUPPRESSION_THRESHOLD="0.70"
export SAM3_MOTION_WINDOW_SECONDS="3.0"
export SAM3_MOTION_THRESHOLD_FRACTION="0.4"

export HF_TOKEN="hf_..."
```

Then in your terminal:

```bash
source config.sh
```

---

## 5. Running detections

Activate your environment and run [`detector.py`](#8-detectorpy--full-scriptfull-script), passing the subdirectory
name as the `--dir` argument. The script constructs the full S3 prefix as:

```
<DATA_PREFIX>/<subdirectory>/
```

All video files under that prefix matching `SAM3_VIDEO_PATTERN` are queued
for processing.

```bash
conda activate seavision
source config.sh   # load environment variables

python scripts/detector.py --dir <subdirectory>
```

The script will:

1. Discover all video files under the constructed S3 prefix that match `SAM3_VIDEO_PATTERN`.
2. Stream each video from S3 and run the SAM3 detector with the configured prompts.
3. Apply the post-processing pipeline (motion tracking → label filtering → NMS).
4. Write a CSV of detections to:

```
<SAM3_OUTPUT_DIRNAME_ROOT>/<DATA_PREFIX>/<subdirectory>/<subdirectory>_detections.csv
```

### Processing multiple directories

To process several subdirectories in a loop:

```bash
for dir in 2026-03-01 2026-03-02 2026-03-03; do
    python scripts/detector.py --dir "$dir"
done
```

---

## 6. Outputs

Detection results are written as CSV files, one per processed subdirectory, at:

```
<SAM3_OUTPUT_DIRNAME_ROOT>/<DATA_PREFIX>/<subdirectory>/<subdirectory>_detections.csv
```

Each row represents a single detection and includes (at minimum) the source
video filename, the timestamp within that video, and the predicted label and
confidence score.

These detections can be vlaidated using the SeaVision [GUI](./gui/Getting%20started.md), 
which can also stream video directly from the AWS source.

---


## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Required environment variable not set` | A config variable was not exported | `source config.sh` before running |
| `No videos found` | Wrong prefix, bucket, or pattern | Double-check `DATA_PREFIX`, `--dir`, and `SAM3_VIDEO_PATTERN` against what is in S3; use `aws s3 ls s3://<bucket>/<prefix>/` to verify |
| AWS auth error | Profile not configured or session expired | Re-run `aws sso login --profile <name>` or check credentials |
| Hugging Face 401 error | Missing or invalid `HF_TOKEN` | Check your token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| CUDA out of memory | Batch size or image size too large | Reduce `SAM3_IMGSZ` or switch to `SAM3_DEVICE=cpu` |

---

## 8. `detector.py` — full script

Place this file at `scripts/detector.py` alongside `config.sh`. It reads all
configuration from environment variables and accepts a single CLI argument
(`--dir`) that selects which S3 subdirectory to process.

```python
#!/usr/bin/env python
"""
Run SAM3 detector via the SeaVision DetectionPipeline on videos from S3.

All configuration is read from environment variables (see config.sh).
The target S3 subdirectory is passed as the --dir CLI argument.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from seavision.pipeline import PipelineConfig


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SAM3 via SeaVision pipeline on S3 videos."
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="S3 subdirectory to process (appended to DATA_PREFIX).",
    )
    return parser.parse_args()


def _get_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value


def _get_env_float(name: str) -> float:
    return float(_get_env(name))


def _get_env_int(name: str) -> int:
    return int(_get_env(name))


def _get_env_csv(name: str) -> List[str]:
    return [part.strip() for part in _get_env(name).split(",") if part.strip()]


def build_pipeline_config(
    subdir: str,
    output_dir: Path,
    prompts: List[str],
    keep_labels: List[str],
    conf_threshold: float,
    iou_thresh: float,
    motion_window_seconds: float,
    motion_threshold_fraction: float,
    checkpoint: str,
    device: str,
    imgsz: int,
) -> "PipelineConfig":
    from seavision.pipeline import PipelineConfig

    config_dict = {
        "input": {"frame_skip": 1},
        "output": {
            "directory": str(output_dir),
            "output_mode": "single",
            "single_file_name": f"{subdir}_detections.csv",
            "overwrite": True,
        },
        "detector": {
            "type": "sam3",
            "config": {
                "checkpoint": checkpoint,
                "device": device,
                "prompts": prompts,
                "confidence_threshold": conf_threshold,
                "video_mode": True,
                "output_masks": False,
                "output_labels": True,
                "imgsz": imgsz,
            },
        },
        "resume": False,
        "postprocess": {
            "stages": [
                {
                    "type": "motion_track_video",
                    "window_seconds": motion_window_seconds,
                    "threshold_fraction": motion_threshold_fraction,
                },
                {
                    "type": "label_filter",
                    "keep_labels": keep_labels,
                },
                {
                    "type": "nms",
                    "iou_threshold": iou_thresh,
                    "class_agnostic": False,
                },
            ]
        },
    }

    return PipelineConfig.from_dict(config_dict)


def main() -> None:
    args = parse_args()

    profile = _get_env("AWS_PROFILE")
    bucket = _get_env("SAM3_S3_BUCKET")
    data_prefix = _get_env("DATA_PREFIX").strip("/")
    pattern = _get_env("SAM3_VIDEO_PATTERN")
    output_dirname_root = _get_env("SAM3_OUTPUT_DIRNAME_ROOT")

    conf_threshold = _get_env_float("SAM3_CONFIDENCE_THRESHOLD")
    iou_thresh = _get_env_float("SAM3_IOU_SUPPRESSION_THRESHOLD")
    motion_window_seconds = _get_env_float("SAM3_MOTION_WINDOW_SECONDS")
    motion_threshold_fraction = _get_env_float("SAM3_MOTION_THRESHOLD_FRACTION")
    device = _get_env("SAM3_DEVICE")
    checkpoint = _get_env("SAM3_CHECKPOINT")
    imgsz = _get_env_int("SAM3_IMGSZ")
    prompts = _get_env_csv("SAM3_PROMPTS")
    keep_labels = _get_env_csv("SAM3_KEEP_LABELS")

    output_dir = Path(output_dirname_root) / data_prefix / args.dir
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{data_prefix}/{args.dir}/"

    logger.info("[CONFIG] Output directory : %s", output_dir)
    logger.info("[CONFIG] AWS profile      : %s", profile)
    logger.info("[CONFIG] S3 bucket        : %s", bucket)
    logger.info("[CONFIG] S3 prefix        : %s", prefix)
    logger.info("[CONFIG] Prompts          : %s", prompts)
    logger.info("[CONFIG] Keep labels      : %s", keep_labels)
    logger.info("[CONFIG] Conf threshold   : %.3f", conf_threshold)
    logger.info("[CONFIG] IoU threshold    : %.2f", iou_thresh)

    os.environ.setdefault("AWS_PROFILE", profile)

    from seavision.engine import discover_s3_videos
    from seavision.engine.detectors.sam3 import SAM3NativeDetector, SAM3DetectorConfig
    from seavision.pipeline import DetectionPipeline

    logger.info("[IMPORTS] SeaVision imports complete.\n")

    logger.info("[S3] Discovering videos...")
    sources = discover_s3_videos(
        bucket=bucket,
        prefix=prefix,
        pattern=pattern,
        profile_name=profile,
    )
    logger.info("[S3] Found %d videos under prefix", len(sources))

    if not sources:
        logger.warning("[S3] No videos found, exiting.")
        return

    pipeline_config = build_pipeline_config(
        subdir=args.dir,
        output_dir=output_dir,
        prompts=list(prompts),
        keep_labels=keep_labels,
        conf_threshold=conf_threshold,
        iou_thresh=iou_thresh,
        motion_window_seconds=motion_window_seconds,
        motion_threshold_fraction=motion_threshold_fraction,
        checkpoint=checkpoint,
        device=device,
        imgsz=imgsz,
    )

    def detector_factory() -> SAM3NativeDetector:
        cfg = SAM3DetectorConfig(
            prompts=list(prompts),
            checkpoint=checkpoint,
            device=device,
            confidence_threshold=conf_threshold,
            video_mode=True,
            output_masks=False,
            output_labels=True,
            imgsz=imgsz,
        )
        return SAM3NativeDetector(cfg)

    pipeline = DetectionPipeline(
        pipeline_config,
        detector_factory=detector_factory,
    )
    result = pipeline.process_sources(sources)
    logger.info(result.summary())


if __name__ == "__main__":
    main()
```

