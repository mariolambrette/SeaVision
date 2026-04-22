# Deploy to Raspberry Pi

The initial operator workflow is manual-copy first. Use SCP, SFTP, or removable
media to transfer the artifact directory to the device.

## Export on the Workstation

```bash
seavision-export --weights models/fish.pt --output ./deployment --target onnx
```

This produces an artifact directory at `./deployment/artifact`.

## Copy to the Device

```bash
scp -r ./deployment/artifact <pi-name>@<pi-ip>:~/seavision-artifact
```

## Install or Update the Runtime
TODO: Ensure these are correct and match the instructions in the wheel runtime
doc.

```bash
python3 -m pip install "<path-to-wheel>[edge]"
```

For development from a checkout on the device:

```bash
python3 -m pip install -e ".[edge]"
```

## Launch

```bash
seavision-edge --artifact-dir ~/seavision-artifact
```

## Smoke Check

For a first-pass smoke check, verify:

1. `seavision-edge --help` runs successfully.
2. Startup validation accepts the copied artifact.
3. A short run produces a detection CSV under the configured output directory.
4. Any validation clips are written when enabled.

Rollback and automated update procedures are not documented yet; those remain a
follow-up item before release readiness.