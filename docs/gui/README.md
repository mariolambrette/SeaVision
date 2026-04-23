# SeaVision GUI — Documentation

The GUI is a desktop tool for reviewing and correcting ML detection
results from the SeaVision pipeline. It lets a reviewer load detection CSVs and
source videos, step through detections frame-by-frame, confirm
or reject each one, correct bounding box geometry, manually add new detections,
and export the validated results for use in downstream model training
applications.

> **This documentation covers the GUI only.** For the detection pipeline, see the
> main SeaVision README and the `engine/` package documentation.

---

## Contents

| Document | Description |
|----------|-------------|
| [Getting Started](./Getting%20started.md) | Installation, launching, and your first session |
| [User Guide](./User%20guide.md) | Complete walkthrough of every feature |
| [Keyboard Shortcuts](./Keyboard%20shortcuts.md) | Quick-reference card |
| [Architecture](./Architecture.md) | Package structure, data flow, threading model |
| [Session File Format](./Session%20format.md) | `.seavision-session` JSON schema reference |
| [S3 & AWS Integration](./S3%20Integration.md) | Working with cloud-stored videos |
| [Smoke Test](./Smoke%20test.md) | Pre-merge manual and automated test procedures |
| [Troubleshooting](./Troubleshooting.md) | Common issues and solutions |

---

## Quick start

1. Clone the Git repository.
```bash
git clone https://github.com/mariolambrette/SeaVision
cd SeaVision
```

2. Install the package in GUI mode.
```bash
pip install -e ".[gui]"
```

3. Launch the app.
```bash
seavision-gui
```

Open a session via **File -> New Session** (`Ctrl+N`), select a
detection CSV and the directory containing the source videos, then start
reviewing. See [Getting Started](./Getting%20started.md) for the full walkthrough.