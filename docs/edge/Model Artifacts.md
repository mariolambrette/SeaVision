# Model Artifacts

`seavision-export` creates the exported model folder used by the SeaVision edge
runtime on the Raspberry Pi.

If you are a field operator using a prepared release folder, start with
[Concepts and Terms](./Concepts%20and%20Terms.md) and
[Operator Quickstart](./Operator%20Quickstart.md). This guide is the technical
reference for the exported model folder itself.

## What this folder is for

The exported model folder, also called the `artifact`, contains more than just
the model file. It also includes:

1. The runtime settings the edge detector should use.
2. Metadata recorded during export.
3. Integrity information used during startup validation.

The edge runtime reads this folder when you run:

```bash
seavision-edge --artifact-dir /path/to/artifact
```

## Artifact Layout

```text
artifact/
|-- manifest.json
|-- config.json
|-- export_metadata.json
`-- <exported-model-filename>.onnx
```

## What each file does

- `manifest.json`: tells SeaVision what files should exist, what their
  checksums should be, and which runtime versions are allowed to use them.
- `config.json`: stores the runtime settings the detector should use on the
  Raspberry Pi.
- `export_metadata.json`: records export-side details such as image size,
  export target, and class labels.
- `<exported-model-filename>.onnx`: the exported detector model itself, for
  example `yolo11n.onnx`.

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

In practice, the important points are:

1. The manifest lists the expected files.
2. The manifest stores checksums so SeaVision can detect damaged or edited
  files.
3. The manifest stores a runtime version range so incompatible package
  versions fail early.

## Artifact integrity rules

Treat the artifact folder as immutable once it has been exported. If any file
inside the folder changes, regenerate the whole artifact so the manifest and
checksums stay correct.

Do not edit these files in place on the Raspberry Pi.

## How this fits into a release folder

For operator releases, place the artifact under a versioned release folder
alongside the SeaVision package file and checksum metadata.

```text
release/
`-- vX.Y.Z/
   |-- wheels/
   |   `-- seavision-X.Y.Z-py3-none-any.whl
   |-- artifacts/
   |   `-- artifact/
   |       |-- manifest.json
   |       |-- config.json
   |       |-- export_metadata.json
   |       `-- <exported-model-filename>.onnx
   `-- checksums/
      `-- SHA256SUMS.txt
```

## Release folder checksums

For production release folders, include `checksums/SHA256SUMS.txt` covering:

1. Wheel file(s) in `wheels/`
2. Artifact files in `artifacts/artifact/`

Example verification:

```bash
cd release/vX.Y.Z
sha256sum -c checksums/SHA256SUMS.txt
```

## Read next

1. [Wheel Runtime](./Wheel%20Runtime.md)
2. [Deploy to Raspberry Pi](./Deploy%20to%20Raspberry%20Pi.md)
3. [Troubleshooting](./Troubleshooting.md)