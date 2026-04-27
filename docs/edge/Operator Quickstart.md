# Operator Quickstart

This guide is for field operators deploying SeaVision edge runtime on a
Raspberry Pi from a prepared release folder.

If you are new to the terminology, read these first:

1. [Concepts and Terms](./Concepts%20and%20Terms.md)
2. [Prerequisites Checklist](./Prerequisites%20Checklist.md)

## What you should already have

You should have received a prepared release folder for one version of the
deployment. In the examples below, that version is written as `vX.Y.Z`.

The release folder should look like this:

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

If one of these items is missing, stop and ask the person who prepared the
deployment package to rebuild it.

## 1. Copy the release folder to the Raspberry Pi

Copy the version folder (`vX.Y.Z`) to this location on the Pi:

- `~/seavision-release/vX.Y.Z`

Choose one method:

1. **SCP (terminal)**

```bash
scp -r ./release/vX.Y.Z <pi-user>@<pi-ip>:~/seavision-release/
```

2. **WinSCP / FileZilla (drag and drop)**
- Host: Pi IP address
- Username/password: Pi login
- Remote folder: `/home/<pi-user>/seavision-release/`
- Drag local `release/vX.Y.Z` into that folder

3. **USB drive**
- Copy `release/vX.Y.Z` to USB on your workstation
- Plug USB into Pi and copy folder to `~/seavision-release/`

When the copy finishes, make sure the folder now exists on the Pi before moving
to the next step.

## 2. Verify the files were copied safely

The checksum step confirms that the copied files are exactly the same as the
original files. This helps catch damaged or incomplete transfers.

Run this on the Raspberry Pi:

```bash
cd ~/seavision-release/vX.Y.Z
sha256sum -c checksums/SHA256SUMS.txt
```

You want to see `OK` next to the files in the release folder. If the checksum
check fails, copy the release folder again before continuing.

## 3. Install the SeaVision runtime

Run the installer script with wheel and artifact paths:

```bash
bash ~/seavision-release/vX.Y.Z/scripts/install_edge_runtime.sh \
    --wheel ~/seavision-release/vX.Y.Z/wheels/seavision-X.Y.Z-py3-none-any.whl \
    --artifact-dir ~/seavision-release/vX.Y.Z/artifacts/artifact \
    --release-version vX.Y.Z
```

The installer does four important things for you:

1. Install or upgrade SeaVision with edge dependencies.
2. Verify `seavision-edge` command exists.
3. Validate `manifest.json` exists in artifact directory.
4. Store the versioned files under `/opt/seavision/` and set the `current`
   paths used by the runtime.

At the end, the script prints the exact launch command to use.

## 4. Launch the detector

Use the command below unless the installer printed a different path:

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

## 5. Confirm the first run worked

You should see all of the following:

1. Runtime starts without startup validation errors.
2. A detections CSV is written to output directory configured in artifact config.
3. Optional validation clips are produced when enabled.

If the runtime exits early, read the error message before retrying. The most
common problems are a damaged copy, a missing file inside the artifact folder,
or the wrong release version being used.

For quick fixes, use [Troubleshooting](./Troubleshooting.md).

## 6. If you need to recover

Use the rollback sequence in [Rollback Runbook](./Rollback%20Runbook.md).

If you need the technical preparation workflow rather than the operator path,
use [Deploy to Raspberry Pi](./Deploy%20to%20Raspberry%20Pi.md).
