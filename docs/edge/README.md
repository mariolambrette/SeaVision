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

## Workflow

1. Export the model and create an artifact directory using `seavision-export`.
2. Copy the artifact directory to the Raspberry Pi.
3. Install or update the SeaVision wheel with the `edge` extra on the Pi.
4. Run `seavision-edge` against the copied artifact directory.
5. Validate the output CSV and optional clips.

## Guides

- [Wheel Runtime](./Wheel%20Runtime.md)
- [Model Artifacts](./Model%20Artifacts.md)
- [Deploy to Raspberry Pi](./Deploy%20to%20Raspberry%20Pi.md)

## Current Status

The wheel-first runtime, artifact manifest loading, checksum validation, and
runtime compatibility checks are implemented. The remaining work before release
is broader smoke coverage, parity testing, and operator rollback runbooks.
