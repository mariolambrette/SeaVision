# Model Artifacts

`seavision-export` creates a model artifact directory to be copied onto the
Raspberry Pi.

## Artifact Layout

```text
artifact/
|-- manifest.json
|-- config.json
|-- export_metadata.json
`-- <exported-model-filename>.onnx
```

## File Roles

- `manifest.json`: runtime compatibility range and integrity metadata.
- `config.json`: edge runtime settings derived from export metadata and CLI
  defaults.
- `export_metadata.json`: export-side metadata such as image size, target, and
  class labels.
- `<exported-model-filename>.onnx`: exported detector model (for example
  `yolo11n.onnx`).

## Manifest Fields

Current manifest fields are:

- `schema_version`
- `artifact_version`
- `runtime_version_range`
- `model.path`
- `model.sha256`
- `runtime_config.path`
- `runtime_config.sha256`
- `export_metadata.path`
- `export_metadata.sha256`

The runtime treats the directory artifact as immutable once exported. Any file
change requires regenerating the manifest so checksum validation remains valid.