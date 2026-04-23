# Wheel Runtime

The edge runtime is delivered through the SeaVision Python package installed
with the correct edge dependencies on the Pi.

## Install

Install or update the package with edge dependencies on the target device.
Preferred operator path:

```bash
bash release/vX.Y.Z/scripts/install_edge_runtime.sh \
    --wheel release/vX.Y.Z/wheels/seavision-X.Y.Z-py3-none-any.whl \
    --artifact-dir release/vX.Y.Z/artifacts/artifact \
    --release-version vX.Y.Z
```

Direct pip alternative:

```bash
python3 -m pip install --upgrade "<path-to-seavision-wheel>[edge]"
```

If you are installing from a local checkout for development:

```bash
python3 -m pip install -e ".[edge]"
```

Verify the install:

```bash
seavision-edge --help
```

## Run

Start the runtime against an exported artifact directory:

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

Optional overrides are available:

```bash
seavision-edge --artifact-dir /opt/seavision/current-artifact --source 0 --conf 0.4 --frame-skip 5
```

## Startup Validation

At startup the runtime validates:

1. The artifact manifest exists.
2. The model, runtime config, and export metadata files exist.
3. Recorded SHA-256 checksums match the artifact contents.
4. The installed SeaVision runtime version satisfies the manifest range.

If any of these checks fail the runtime exits before ONNX loading starts.