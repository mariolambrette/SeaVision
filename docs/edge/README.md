# Edge Deployment

This section covers how to run a SeaVision model directly on a Raspberry Pi.

If you are new to deployment work, read the documents in this order:

1. [Concepts and Terms](./Concepts%20and%20Terms.md)
2. [Prerequisites Checklist](./Prerequisites%20Checklist.md)
3. [Operator Quickstart](./Operator%20Quickstart.md)

## What edge deployment does

Edge deployment runs the detector on the Raspberry Pi itself instead of sending
all video back to a larger computer for processing. The result is usually:

1. Less data transfer.
2. Lower power and compute use away from the workstation.
3. Detection CSV files created directly on the device.
4. Optional validation clips written on the device when enabled.

## Choose the right guide

### I am a field operator

Use these guides if someone has already prepared the deployment files for you.

1. [Concepts and Terms](./Concepts%20and%20Terms.md)
2. [Prerequisites Checklist](./Prerequisites%20Checklist.md)
3. [Operator Quickstart](./Operator%20Quickstart.md)
4. [Troubleshooting](./Troubleshooting.md)
5. [Rollback Runbook](./Rollback%20Runbook.md)

### I am preparing the deployment package

Use these guides if you are exporting the model, assembling release files, or
checking the technical file layout.

1. [Deploy to Raspberry Pi](./Deploy%20to%20Raspberry%20Pi.md)
2. [Model Artifacts](./Model%20Artifacts.md)
3. [Wheel Runtime](./Wheel%20Runtime.md)

## Core idea

SeaVision edge deployment uses two things on the Raspberry Pi:

1. The SeaVision runtime installed on the device.
2. An exported model folder copied onto the device.

The operator guides use the plain-language term `release folder` for the set of
files copied to the Pi. The technical docs may also call this a `release
bundle`.

## Success looks like this

An edge deployment is working when:

1. `seavision-edge --help` runs on the Pi.
2. `seavision-edge --artifact-dir /opt/seavision/current-artifact` starts
   without validation errors.
3. A detections CSV appears in the output directory defined by the artifact
   config.
4. Validation clips appear if they were enabled during export.

## Related references

- [Concepts and Terms](./Concepts%20and%20Terms.md)
- [Prerequisites Checklist](./Prerequisites%20Checklist.md)
- [Operator Quickstart](./Operator%20Quickstart.md)
- [Troubleshooting](./Troubleshooting.md)
- [Deploy to Raspberry Pi](./Deploy%20to%20Raspberry%20Pi.md)
- [Model Artifacts](./Model%20Artifacts.md)
- [Wheel Runtime](./Wheel%20Runtime.md)
- [Rollback Runbook](./Rollback%20Runbook.md)
