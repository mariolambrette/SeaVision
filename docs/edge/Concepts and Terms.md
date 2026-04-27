# Edge Deployment Concepts and Terms

This guide explains the words used in the edge deployment docs before you start
running commands.

## The basic picture

SeaVision edge deployment happens in five stages:

1. A model is exported on a workstation.
2. The deployment files are placed into a release folder.
3. That release folder is copied to the Raspberry Pi.
4. The installer sets up SeaVision on the Pi.
5. `seavision-edge` runs using the exported model folder.

## Terms you will see

### Release folder

The `release folder` is the folder copied to the Raspberry Pi for one specific
deployment version. It usually contains:

1. An installer script.
2. A SeaVision package file.
3. An exported model folder.
4. A checksum file used to confirm nothing was damaged during transfer.

Some technical docs call this a `release bundle`. In operator-facing docs, both
phrases mean the same thing.

### Wheel

A `wheel` is a packaged Python application file. In SeaVision, the wheel is the
file that installs the edge runtime on the Raspberry Pi.

If you see a file such as `seavision-X.Y.Z-py3-none-any.whl`, that is the wheel.

### Artifact

An `artifact` is the exported model folder used by `seavision-edge`. It is not
just the model file on its own. It also includes metadata and configuration
that tell SeaVision how to run the model safely.

### Manifest

The `manifest.json` file is a small description file inside the artifact. It
helps SeaVision check that the artifact is complete and compatible with the
runtime installed on the Pi.

### Checksum

A `checksum` is a fingerprint for a file. SeaVision uses checksum files so you
can confirm the copied files are identical to the originals.

This matters because a damaged or incomplete file transfer can make a
deployment fail even when the folder names look correct.

### ONNX

`ONNX` is the model file format currently used by the SeaVision edge runtime.
You do not need to understand the format in detail to deploy it. In practice,
it is the exported model file that the runtime reads on the device.

### Current or stable pointer

A `current pointer` or `stable pointer` is a fixed path on the Raspberry Pi
that always points to the deployment version SeaVision should use right now.

For example, `/opt/seavision/current-artifact` points to the artifact folder
that should be used by `seavision-edge`.

This allows upgrades and rollbacks without changing every command.

### Semantic version

A `semantic version` is a version number such as `1.4.2`. SeaVision docs often
show this as `vX.Y.Z` when they mean “replace this with the real version”.

For example:

- `v1.4.2` is a real version.
- `vX.Y.Z` is a placeholder.

## What you need to remember

If you are not preparing the deployment package yourself, the main things to
remember are:

1. You need a prepared release folder.
2. That release folder contains the SeaVision installer and the exported model.
3. The Raspberry Pi runs `seavision-edge` against the exported model folder.
4. The installer sets the `current` paths used by the runtime.

## Read next

1. [Prerequisites Checklist](./Prerequisites%20Checklist.md)
2. [Operator Quickstart](./Operator%20Quickstart.md)