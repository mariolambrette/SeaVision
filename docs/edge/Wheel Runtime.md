# Wheel Runtime

The edge runtime is delivered through the SeaVision Python package installed
with the correct edge dependencies on the Pi.

## Install

TODO: The install instructions for the edge wheel need to be checked and
updated as necessary.

Install the package with edge dependencies on the target device:

```bash
python -m pip install "<path-to-wheel>[edge]"
```

If you are installing from a local checkout for development:

```bash
python -m pip install -e ".[edge]"
```

## Run

Start the runtime against an exported artifact directory:

```bash
seavision-edge --artifact-dir /path/to/artifact
```

Optional overrides are available:

```bash
seavision-edge --artifact-dir /path/to/artifact --source 0 --conf 0.4 --frame-skip 5
```

## Startup Validation

At startup the runtime validates:

1. The artifact manifest exists.
2. The model, runtime config, and export metadata files exist.
3. Recorded SHA-256 checksums match the artifact contents.
4. The installed SeaVision runtime version satisfies the manifest range.

If any of these checks fail the runtime exits before ONNX loading starts.