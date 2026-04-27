# Wheel Runtime

This guide explains the SeaVision package installed on the Raspberry Pi for
edge detection.

If you are a field operator using a prepared release folder, use
[Operator Quickstart](./Operator%20Quickstart.md) first. This guide is the
technical reference for the installed runtime and its validation behavior.

## What the runtime is

The `wheel runtime` means the SeaVision package file installed on the Raspberry
Pi with the edge dependencies it needs to run exported models.

In operator docs, this is usually described more simply as `the SeaVision
runtime installed on the device`.

## Install

Install or update the package with edge dependencies on the target device.

### Preferred path for prepared release folders

```bash
bash release/vX.Y.Z/scripts/install_edge_runtime.sh \
    --wheel release/vX.Y.Z/wheels/seavision-X.Y.Z-py3-none-any.whl \
    --artifact-dir release/vX.Y.Z/artifacts/artifact \
    --release-version vX.Y.Z
```

This installer script:

1. Installs the SeaVision package file with edge dependencies.
2. Checks that the `seavision-edge` command is available.
3. Confirms the exported model folder contains a manifest.
4. Optionally stores the version under `/opt/seavision/releases/` for rollback.
5. Updates `/opt/seavision/current-artifact` to the active artifact path.

### Direct package install

Use this when you do not have the prepared installer script flow:

```bash
python3 -m pip install --upgrade "<path-to-seavision-wheel>[edge]"
```

### Development install from a checkout

If you are installing from a local checkout for development:

```bash
python3 -m pip install -e ".[edge]"
```

## Verify the install

```bash
seavision-edge --help
```

You should see the command help text rather than a `command not found` error.

## Run

Start the runtime against an exported artifact directory:

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

Optional overrides are available:

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact --source 0 --conf 0.4 --frame-skip 5
```

If you used the installer script with `--release-version`, the
`/opt/seavision/current-artifact` path is the stable path you should normally
use.

## Startup Validation

At startup the runtime validates:

1. The artifact manifest exists.
2. The model, runtime config, and export metadata files exist.
3. Recorded SHA-256 checksums match the artifact contents.
4. The installed SeaVision runtime version satisfies the manifest range.

If any of these checks fail, the runtime exits before model loading starts.

This early stop is intentional. It prevents the device from running with a
damaged, incomplete, or incompatible exported model folder.

## Read next

1. [Model Artifacts](./Model%20Artifacts.md)
2. [Troubleshooting](./Troubleshooting.md)
3. [Rollback Runbook](./Rollback%20Runbook.md)