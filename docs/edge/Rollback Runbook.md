# Rollback Runbook

This runbook defines the operator rollback procedure for SeaVision edge runtime.

## Preconditions

1. Versioned runtime assets are stored under `/opt/seavision/releases`.
2. Stable pointers are used:
   - `/opt/seavision/current-wheel`
   - `/opt/seavision/current-artifact`
3. At least one previous release exists.

Expected structure:

```text
/opt/seavision/
|-- current-wheel -> /opt/seavision/releases/wheels/vX.Y.Z
|-- current-artifact -> /opt/seavision/releases/artifacts/vX.Y.Z
`-- releases/
    |-- wheels/
    |   |-- vX.Y.Z/
    |   `-- vX.Y.(Z-1)/
    `-- artifacts/
        |-- vX.Y.Z/
        `-- vX.Y.(Z-1)/
```

## Single rollback sequence

Replace `vPREV` with the target previous release version.

```bash
# 1) Reinstall the previous wheel with edge dependencies
PREV_WHEEL=$(ls /opt/seavision/releases/wheels/vPREV/seavision-*.whl | head -n 1)
python3 -m pip install --upgrade "${PREV_WHEEL}[edge]"

# 2) Switch stable pointers to previous release
ln -sfn "/opt/seavision/releases/wheels/vPREV" /opt/seavision/current-wheel
ln -sfn "/opt/seavision/releases/artifacts/vPREV" /opt/seavision/current-artifact

# 3) Verify runtime command still resolves
seavision-edge --help

# 4) Launch runtime using stable artifact pointer
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

## Rollback verification checklist

1. `seavision-edge --help` succeeds.
2. Runtime passes startup validation checks.
3. Detection CSV output is created.
4. No import errors occur during startup.

## Notes

1. Keep at least two release versions on each device.
2. Do not modify artifact directory contents in-place; artifacts are immutable.
3. If storage is limited, remove only versions older than the previous known-good release.
