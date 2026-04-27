# Edge Deployment Prerequisites Checklist

Use this checklist before you start copying files or running installer
commands.

## Who this guide is for

This guide is for field operators and deployment staff using a prepared release
folder on a Raspberry Pi.

## You need access to

### On the workstation or source computer

- The prepared SeaVision release folder for the version you are deploying.
- A way to copy files to the Raspberry Pi: `scp`, WinSCP, FileZilla, or a USB
  drive.
- The Raspberry Pi login details.

### On the Raspberry Pi

- Raspberry Pi OS 64-bit.
- Python 3.10 or newer.
- Enough free storage for the release folder and output files.
- Permission to run install commands and write to `/opt/seavision/`.

## The release folder should contain

Before you begin, confirm the release folder includes these items:

```text
release/
`-- vX.Y.Z/
    |-- scripts/
    |   `-- install_edge_runtime.sh
    |-- wheels/
    |   `-- seavision-X.Y.Z-py3-none-any.whl
    |-- artifacts/
    |   `-- artifact/
    |       |-- manifest.json
    |       |-- config.json
    |       |-- export_metadata.json
    |       `-- <exported-model-filename>.onnx
    |-- checksums/
    |   `-- SHA256SUMS.txt
    `-- OPERATOR_QUICKSTART.md
```

If one of these parts is missing, stop and ask the person who prepared the
deployment package to rebuild it.

## Before you start, confirm these points

- You know which release version you are installing.
- You know where the release folder will be copied on the Pi.
- You know how to open a terminal on the Pi.
- You know whether you are transferring files over the network or by USB.
- You understand that `vX.Y.Z` in the docs is a placeholder and must be
  replaced with the real version.

## Quick verification commands

Run these on the Raspberry Pi before installation if you need a basic check:

```bash
python3 --version
python3 -m pip --version
mkdir -p ~/seavision-release
```

You are ready to continue when:

1. Python 3 is available.
2. `pip` is available.
3. You can create or access `~/seavision-release`.
4. You have the prepared release folder and Pi login details.

## Read next

1. [Operator Quickstart](./Operator%20Quickstart.md)
2. [Rollback Runbook](./Rollback%20Runbook.md)