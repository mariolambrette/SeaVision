# Deploy to Raspberry Pi

This guide is for the person preparing the SeaVision deployment package before
it is handed to a field operator.

If you are the person running commands on the Raspberry Pi from a prepared
release folder, use [Operator Quickstart](./Operator%20Quickstart.md) instead.

If you are new to the terminology, start with
[Concepts and Terms](./Concepts%20and%20Terms.md).

## What this guide covers

This guide covers the technical preparation flow:

1. Export the model on a workstation.
2. Assemble the release folder.
3. Copy the release folder to the Raspberry Pi.
4. Install SeaVision on the Pi.
5. Run a first smoke check.

## Release folder structure

This guide assumes the release folder follows:

```text
release/vX.Y.Z/
|-- scripts/
|-- wheels/
|-- artifacts/
|-- checksums/
`-- OPERATOR_QUICKSTART.md
```

## 1. Export on the workstation

```bash
seavision-export --weights models/fish.pt --output ./deployment --target onnx
```

This produces an artifact directory at `./deployment/artifact`.

## 2. Assemble the release folder

Place the wheel and artifact into a versioned release folder before transfer.
Also copy the installer script from this repository to
`release/vX.Y.Z/scripts/install_edge_runtime.sh`.

At a minimum, the release folder should contain:

1. The SeaVision wheel in `wheels/`.
2. The exported artifact folder in `artifacts/`.
3. The installer script in `scripts/`.
4. The checksum file in `checksums/`.
5. The operator instructions shipped with the release.

Use [Model Artifacts](./Model%20Artifacts.md) if you need the technical file
contract for the exported model folder.

## 3. Copy to the device

Copy `release/vX.Y.Z` to `~/seavision-release/` on the Pi.

Terminal option:

```bash
scp -r ./release/vX.Y.Z <pi-name>@<pi-ip>:~/seavision-release/
```

Drag-and-drop option (WinSCP / FileZilla):

1. Connect to the Pi (host, username, password)
2. Open remote folder `/home/<pi-user>/seavision-release/`
3. Drag local `release/vX.Y.Z` into that folder

USB option:

1. Copy `release/vX.Y.Z` to a USB drive
2. Plug USB into Pi
3. Copy folder into `~/seavision-release/`

## 4. Minimal install path on the Raspberry Pi

If you only need one path to follow:

```bash
# 1) Copy release folder
scp -r ./release/vX.Y.Z <pi-name>@<pi-ip>:~/seavision-release/

# 2) SSH into Pi
ssh <pi-name>@<pi-ip>

# 3) Install runtime and set current pointers
bash ~/seavision-release/vX.Y.Z/scripts/install_edge_runtime.sh \
    --wheel ~/seavision-release/vX.Y.Z/wheels/seavision-X.Y.Z-py3-none-any.whl \
    --artifact-dir ~/seavision-release/vX.Y.Z/artifacts/artifact \
    --release-version vX.Y.Z

# 4) Run detector
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

This installs the edge runtime, checks that the artifact contains a manifest,
stores the version under `/opt/seavision/releases/`, and points
`/opt/seavision/current-artifact` at the active artifact.

## 5. Install or update the runtime

```bash
bash ~/seavision-release/vX.Y.Z/scripts/install_edge_runtime.sh \
    --wheel ~/seavision-release/vX.Y.Z/wheels/seavision-X.Y.Z-py3-none-any.whl \
    --artifact-dir ~/seavision-release/vX.Y.Z/artifacts/artifact \
    --release-version vX.Y.Z
```

For development from a checkout on the device:

```bash
python3 -m pip install -e ".[edge]"
```

## 6. Launch

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

## 7. Smoke check

For a first-pass smoke check, verify:

1. `seavision-edge --help` runs successfully.
2. Startup validation accepts the copied artifact.
3. A short run produces a detection CSV under the configured output directory.
4. Any validation clips are written when enabled.

## 8. Hand off to the operator

Once the release folder has been prepared and tested, hand the operator these
docs in order:

1. [Concepts and Terms](./Concepts%20and%20Terms.md)
2. [Prerequisites Checklist](./Prerequisites%20Checklist.md)
3. [Operator Quickstart](./Operator%20Quickstart.md)

## Troubleshooting

Use [Troubleshooting](./Troubleshooting.md) for the quick-check table and the
most common operator and deployment fixes.

## Rollback

Use the single rollback sequence in:

- [Rollback Runbook](./Rollback%20Runbook.md)