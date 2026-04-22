"""
CLI entry point for the SeaVision edge runtime.

Usage:
    seavision-edge                           # Use config.json
    seavision-edge --config myconfig.json
    seavision-edge --source 0                # Camera 0
    seavision-edge --source video.mp4        # Video file
"""

import argparse
import sys


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="seavision-edge",
        description="SeaVision edge inference runtime",
    )
    parser.add_argument(
        "--config", default="config.json",
        help="Path to config.json (default: config.json)",
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

    from seavision.edge import EdgeConfig, EdgeRuntime

    try:
        config = EdgeConfig.from_file(args.config)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {args.config}")
        print("Run seavision-export first to create a deployment bundle.")
        return 1

    # Apply CLI overrides
    if args.source is not None:
        config.source = args.source
    if args.conf is not None:
        config.conf_threshold = args.conf
    if args.frame_skip is not None:
        config.frame_skip = args.frame_skip

    runtime = EdgeRuntime(config)
    runtime.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
