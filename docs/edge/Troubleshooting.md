# Edge Troubleshooting

Use this guide when the SeaVision edge deployment does not install, launch, or
produce output as expected.

If you are new to the deployment flow, start with
[Operator Quickstart](./Operator%20Quickstart.md) before using the fixes below.

## Quick checks

| Problem | What it usually means | Quick check | Fix |
|---|---|---|---|
| `seavision-edge` command missing | SeaVision was not installed in the active Python environment | `python3 -m pip show seavision` | Reinstall with `python3 -m pip install --upgrade "<path-to-seavision-wheel>[edge]"` or rerun the installer script |
| Import error for `onnxruntime` | Edge dependencies are missing or the wrong environment is active | `python3 -m pip show onnxruntime` | Reinstall the SeaVision wheel with `[edge]` dependencies |
| Checksum verification fails | One or more copied files do not match the original release folder | `cd ~/seavision-release/vX.Y.Z` then `sha256sum -c checksums/SHA256SUMS.txt` | Copy the release folder again before installing |
| Artifact rejected at startup | The exported model folder is incomplete, damaged, or incompatible | `seavision-edge --artifact-dir /opt/seavision/current-artifact` | Recreate the artifact with `seavision-export` and copy the complete folder again |
| `manifest.json` missing during install | The installer was pointed at the wrong folder | Check whether the artifact is at `<path>/manifest.json` or `<path>/artifact/manifest.json` | Rerun the installer with the artifact folder or its parent directory |
| No output CSV after launch | The runtime started but could not write output where the config expects | Check `config.json` output settings and the target directory permissions | Fix the output path or permissions, then rerun the detector |
| New release fails and previous version worked | The active release may be broken or incompatible | Compare the current version against the previous known-good version | Use [Rollback Runbook](./Rollback%20Runbook.md) to restore the previous release |

## Good first commands

Use these commands when you need a quick status check on the Raspberry Pi:

```bash
seavision-edge --help
python3 -m pip show seavision
python3 -m pip show onnxruntime
seavision-edge --artifact-dir /opt/seavision/current-artifact
```

## When to stop and rebuild

Do not keep retrying the same install if:

1. The checksum check fails more than once.
2. `manifest.json` is missing from the exported model folder.
3. The runtime reports version incompatibility between the package and the
   artifact.

In those cases, rebuild the release folder or request a new one from the person
who prepared it.

## Read next

1. [Operator Quickstart](./Operator%20Quickstart.md)
2. [Rollback Runbook](./Rollback%20Runbook.md)
3. [Wheel Runtime](./Wheel%20Runtime.md)