# Edge Deployment

Users may wish to deploy models developed or refined using SeaVision to an edge
device. Full support is provided for deploying trained model weight files
(`*.pt`) on Raspberry Pi.

Edge deployment creates SeaVision detection files directly on the Pi which may
save compute time, power and data transfer requirements. Users can optionally
export periodic validation clips alongside the detections.

SeaVision edge deployment relies on two components:

1. A SeaVision wheel with edge dependencies installed on the Pi.
2. A model artifact directory produced by `seavision-export`.

## Frozen release artifact layout

Use a versioned release directory so upgrades and rollbacks are deterministic:

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

## Install and verify

Install or update the runtime on the Pi using the operator script:

```bash
bash release/vX.Y.Z/scripts/install_edge_runtime.sh \
    --wheel release/vX.Y.Z/wheels/seavision-X.Y.Z-py3-none-any.whl \
    --artifact-dir release/vX.Y.Z/artifacts/artifact \
    --release-version vX.Y.Z
```

Verify the runtime command is available:

```bash
seavision-edge --help
```

## Workflow

1. Export the model and create an artifact directory using `seavision-export`.
2. Build a versioned release folder (`release/vX.Y.Z`) with wheel, artifact,
   checksums, bundled installer script, and operator quickstart.
3. Copy the release folder to the Raspberry Pi.
4. Install or update SeaVision with `release/vX.Y.Z/scripts/install_edge_runtime.sh`.
5. Launch runtime using the stable artifact pointer.
6. Validate the output CSV and optional clips.

## First-run checks

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

Confirm:

1. Startup validation passes (manifest, required files, checksums, version range).
2. A detections CSV is written to the configured output directory.
3. Validation clips are written if enabled in config.

## Troubleshooting quick checks

| Problem | Quick check | Fix |
|---|---|---|
| `seavision-edge` not found | `python3 -m pip show seavision` | Reinstall with `python3 -m pip install --upgrade "<path-to-seavision-wheel>[edge]"` |
| Missing `onnxruntime` import | `python3 -m pip show onnxruntime` | Reinstall edge extra as above |
| Startup validation fails | Review `seavision-edge --artifact-dir <path>` output | Re-export artifact with `seavision-export` and copy full directory again |
| Runtime exits immediately on version check | Compare package version vs manifest range | Install matching SeaVision wheel version |

## Guides

- [Operator Quickstart](./Operator%20Quickstart.md)
- [Wheel Runtime](./Wheel%20Runtime.md)
- [Model Artifacts](./Model%20Artifacts.md)
- [Deploy to Raspberry Pi](./Deploy%20to%20Raspberry%20Pi.md)
- [Rollback Runbook](./Rollback%20Runbook.md)

If you are not comfortable with command-line tooling, start with
[Operator Quickstart](./Operator%20Quickstart.md) and use the transfer section
that covers WinSCP/FileZilla and USB workflows.

## Current Status

The wheel-first runtime, artifact manifest loading, checksum validation,
runtime compatibility checks, operator installer workflow, and rollback
runbook are implemented. Remaining release work is broader smoke coverage and
parity testing on target devices.
