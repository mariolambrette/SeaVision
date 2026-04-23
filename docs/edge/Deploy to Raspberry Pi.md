# Deploy to Raspberry Pi

This guide is written for operators who want a predictable copy-and-run
workflow.

This guide assumes the release bundle follows:

```text
release/vX.Y.Z/
|-- scripts/
|-- wheels/
|-- artifacts/
|-- checksums/
`-- OPERATOR_QUICKSTART.md
```

## Export on the Workstation

```bash
seavision-export --weights models/fish.pt --output ./deployment --target onnx
```

This produces an artifact directory at `./deployment/artifact`.

Place the wheel and artifact into a versioned release folder before transfer.
Also copy the installer script from this repository to
`release/vX.Y.Z/scripts/install_edge_runtime.sh`.

## Copy to the Device

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

## Minimal operator path (copy/paste)

If you only need one path to follow:

```bash
# 1) Copy release bundle
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

## Install or Update the Runtime

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

## Launch

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

## Smoke Check

For a first-pass smoke check, verify:

1. `seavision-edge --help` runs successfully.
2. Startup validation accepts the copied artifact.
3. A short run produces a detection CSV under the configured output directory.
4. Any validation clips are written when enabled.

## Troubleshooting quick checks

| Problem | Quick check | Fix |
|---|---|---|
| `seavision-edge` command missing | `python3 -m pip show seavision` | Reinstall with `python3 -m pip install --upgrade "<path-to-seavision-wheel>[edge]"` |
| Import error for ONNX Runtime | `python3 -m pip show onnxruntime` | Reinstall edge extra as above |
| Artifact rejected at startup | `seavision-edge --artifact-dir /opt/seavision/current-artifact` logs | Recreate artifact with `seavision-export` and copy the complete folder |
| No output CSV after launch | Check `config.json` output_dir in artifact | Ensure write permissions and rerun with correct artifact directory |

## Rollback

Use the single rollback sequence in:

- [Rollback Runbook](./Rollback%20Runbook.md)