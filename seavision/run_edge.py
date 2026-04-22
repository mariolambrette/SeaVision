"""
CLI entry point for the SeaVision edge runtime.

Usage:
    seavision-edge                           # Use artifact in current directory
    seavision-edge --artifact-dir ./artifact
    seavision-edge --source 0                # Camera 0
    seavision-edge --source video.mp4        # Video file
"""

import argparse
import sys
from pathlib import Path


def _load_runtime_class():
    """Import the runtime only when startup validation has passed."""
    from seavision.edge import EdgeRuntime

    return EdgeRuntime


def _resolve_artifact_dir(path: str, manifest_filename: str) -> str:
    """Resolve artifact directory, auto-selecting a nested artifact folder."""
    artifact_dir = Path(path)
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        return path

    if (artifact_dir / manifest_filename).exists():
        return str(artifact_dir)

    nested_artifact_dir = artifact_dir / "artifact"
    if (nested_artifact_dir / manifest_filename).exists():
        return str(nested_artifact_dir)

    return str(artifact_dir)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="seavision-edge",
        description="SeaVision edge inference runtime",
    )
    parser.add_argument(
        "--artifact-dir", default=".",
        help="Path to the exported model artifact directory (default: current directory)",
    )
    parser.add_argument(
        "--source", default=None,
        help="Override video source (camera index or file path)",
    )
    parser.add_argument(
        "--conf", type=float, default=None,
        help="Override confidence threshold",
    )
    parser.add_argument(
        "--frame-skip", type=int, default=None,
        help="Override frame skip",
    )

    args = parser.parse_args()

    from seavision.edge import EdgeConfig
    from seavision.edge.config import ARTIFACT_MANIFEST_FILENAME

    resolved_artifact_dir = _resolve_artifact_dir(
        args.artifact_dir, ARTIFACT_MANIFEST_FILENAME
    )

    try:
        config = EdgeConfig.from_artifact_dir(resolved_artifact_dir)
    except FileNotFoundError:
        print(
            "ERROR: Artifact directory is incomplete or missing required files: "
            f"{args.artifact_dir}"
        )
        print("Run seavision-export first to create an edge artifact directory.")
        return 1

    # Apply CLI overrides
    if args.source is not None:
        config.source = args.source
    if args.conf is not None:
        config.conf_threshold = args.conf
    if args.frame_skip is not None:
        config.frame_skip = args.frame_skip

    EdgeRuntime = _load_runtime_class()
    runtime = EdgeRuntime(config)
    runtime.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
