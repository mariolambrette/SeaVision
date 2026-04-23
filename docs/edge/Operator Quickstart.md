# Operator Quickstart

This guide is intended for field operators deploying SeaVision edge runtime on
Raspberry Pi from a prepared release bundle.

## Release bundle contract

Each release should provide a versioned directory with:

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

## How to get this folder onto the Raspberry Pi

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

## 1. Verify checksums

On the target device (or before transfer), verify release integrity:

```bash
cd ~/seavision-release/vX.Y.Z
sha256sum -c checksums/SHA256SUMS.txt
```

## 2. Install and activate runtime

Run the installer script with wheel and artifact paths:

```bash
bash ~/seavision-release/vX.Y.Z/scripts/install_edge_runtime.sh \
    --wheel ~/seavision-release/vX.Y.Z/wheels/seavision-X.Y.Z-py3-none-any.whl \
    --artifact-dir ~/seavision-release/vX.Y.Z/artifacts/artifact \
    --release-version vX.Y.Z
```

The installer will:

1. Install or upgrade SeaVision with edge dependencies.
2. Verify `seavision-edge` command exists.
3. Validate `manifest.json` exists in artifact directory.
4. Set stable pointers under `/opt/seavision/current-*`.
5. Print the exact launch command.

## 3. Launch runtime

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

## 4. First-run success checks

1. Runtime starts without startup validation errors.
2. A detections CSV is written to output directory configured in artifact config.
3. Optional validation clips are produced when enabled.

## 5. Rollback (single sequence)

Use the rollback sequence in [Rollback Runbook](./Rollback%20Runbook.md).
