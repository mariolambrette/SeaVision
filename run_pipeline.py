#!/usr/bin/env python
"""Command line interface for the buoy detection pipeline."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import yaml

from engine import discover_local_videos, discover_s3_videos
from pipeline import(
    DetectionPipeline,
    PipelineConfig,
    InputConfig,
    DetectorConfig,
    setup_logging,
)
from engine import PostprocessorConfig, OutputMode


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    
    parser = argparse.ArgumentParser(
        description="Buoy detection pipeline - object detection in buoy footage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  # Process local videos
  python run_pipeline.py --input ./footage/ --output ./results/

  # Process a single video
  python run_pipeline.py --input ./footage/video.ts --output ./results/

  # Use a config file
  python run_pipeline.py --config config/default.yaml

  # Dry run (scan without processing)
  python run_pipeline.py --input ./footage/ --dry-run

  # Resume interrupted processing
  python run_pipeline.py --input ./footage/ --output ./results/ --resume

  # Quick preview (every 10th frame)
  python run_pipeline.py --input ./footage/ --frame-skip 10
        """,
    )

    # Input options
    input_group = parser.add_argument_group("Input options")
    input_group.add_argument(
        "--input", "-i",
        type=str,
        help="Path to video file or directory containing videos.",
    )
    input_group.add_argument(
        "--pattern", "-p",
        type=str,
        default="*.ts",
        help="Glob pattern for matching videos in a directory (default: *.ts).",
    )
    input_group.add_argument(
        "--source-type",
        type=str,
        choices=["local", "s3"],
        default=None,
        help="Video source type (default: local). Can be set in config file.",
    )
    input_group.add_argument(
        "--s3-bucket",
        type=str,
        help="S3 bucket name (for s3 source type).",
    )
    input_group.add_argument(
        "--s3-prefix",
        type=str,
        help="S3 prefix/path (for s3 source type).",
    )
    input_group.add_argument(
        "--s3-profile",
        type=str,
        help="AWS SSO profile name (for s3 source type).",
    )

    # Output options
    output_group = parser.add_argument_group("Output options")
    output_group.add_argument(
        "--output", "-o",
        type=str,
        default="./output",
        help="Output directory for detection CSV files (default: ./output).",
    )
    output_group.add_argument(
        "--single-file",
        action="store_true",
        help="Write all detections to a single CSV file instead of per-video.",
    )
    output_group.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )

    # Processing options
    proc_group = parser.add_argument_group("Processing options")
    proc_group.add_argument(
        "--frame-skip",
        type=int,
        default=1,
        help="Process every Nth frame (default: 1, all frames).",
    )
    proc_group.add_argument(
        "--resume",
        action="store_true",
        help="Skip videos that already have output files.",
    )
    proc_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan videos and report statistics without processing.",
    )

    # Detector options
    det_group = parser.add_argument_group("Detector options")
    det_group.add_argument(
        "--detector",
        type=str,
        default="motion",
        help="Detector type to use (default: motion).",
    )
    det_group.add_argument(
        "--min-area",
        type=int,
        help="Minimum contour area in pixels (motion detector).",
    )
    det_group.add_argument(
        "--max-area",
        type=int,
        help="Maximum contour area in pixels (motion detector).",
    )
    det_group.add_argument(
        "--no-stabilisation",
        action="store_true",
        help="Disable frame stabilisation (motion detector).",
    )

    # Config file
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to YAML configuration file. CLI args override config file values.",
    )

    # Logging
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging.",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress info logging, only show warnings and errors.",
    )

    return parser.parse_args()


def load_config_file(config_path: str) -> dict:
    """
    Load configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Dictionary with configuration values.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_config(args: argparse.Namespace) -> PipelineConfig:
    """
    Build PipelineConfig from CLI arguments and optional config file.

    Precendence: CLI args > config file > defaults.

    Args:
        args: Parsed command line arguments.
    
    Returns:
        PipelineConfig object with merged configuration.
    """
    # Start with defaults or config file
    if args.config:
        config_data = load_config_file(args.config)
        config = PipelineConfig.from_dict(config_data)
    else:
        config = PipelineConfig()

    # Override with CLI arguments
    if args.frame_skip != 1:
        config.input = InputConfig(frame_skip=args.frame_skip)

    if args.output:
        config.output.output_dir = args.output
    if args.single_file:
        config.output.output_mode = OutputMode.SINGLE_FILE
    if args.overwrite:
        config.output.overwrite = True

    if args.resume:
        config.resume = True

    # Detector config overrides
    if args.detector:
        config.detector.type = args.detector

    detector_overrides = {}
    if args.min_area is not None:
        detector_overrides["min_area"] = args.min_area
    if args.max_area is not None:
        detector_overrides["max_area"] = args.max_area
    if args.no_stabilisation:
        detector_overrides["stabilisation_enabled"] = False

    if detector_overrides:
        # Merge with existing detector config
        config.detector.config.update(detector_overrides)

    return config


def discover_sources(args: argparse.Namespace, config_data: dict = None):
    """
    Discover video sources based on CLI arguments and config file.

    Args:
        args: Parsed command-line arguments.
        config_data: Configuration data from YAML file (optional).

    Returns:
        List of VideoSource instances.

    Raises:
        ValueError: If no input path is specified.
    """
    config_data = config_data or {}
    input_config = config_data.get("input", {})
    s3_config = input_config.get("s3", {})
    
    # Determine input path (CLI takes precedence)
    input_path = args.input or input_config.get("path")
    if not input_path:
        raise ValueError(
            "No input specified. Use --input or set input.path in config file."
        )
    
    # Determine source type (CLI takes precedence)
    source_type = args.source_type or input_config.get("source_type", "local")
    
    # Determine pattern (CLI takes precedence)
    pattern = args.pattern if args.pattern != "*.ts" else input_config.get("pattern", "*.ts")

    if source_type == "local":
        return discover_local_videos(input_path, pattern)
    elif source_type == "s3":
        # Get S3 settings (CLI takes precedence over config)
        bucket = args.s3_bucket or s3_config.get("bucket") or input_path
        prefix = args.s3_prefix or s3_config.get("prefix", "")
        profile = args.s3_profile or s3_config.get("profile_name")
        
        return discover_s3_videos(
            bucket=bucket,
            prefix=prefix,
            pattern=pattern,
            profile_name=profile
        )
    else:
        raise ValueError(f"Unknown source type: {source_type}")
    

def main() -> int:
    """
    Main entry point for the CLI.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    args = parse_args()

    # Set up logging
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING
    else:
        log_level = logging.INFO
    setup_logging(log_level)

    logger = logging.getLogger(__name__)

    try:
        # Load config file if specified
        config_data = {}
        if args.config:
            config_data = load_config_file(args.config)
        
        # Build configuration
        config = build_config(args)

        # Discover video sources
        sources = discover_sources(args, config_data)
        logger.info(f"Discovered {len(sources)} video source(s).")

        # Create and run pipeline
        pipeline = DetectionPipeline(config)
        result = pipeline.process_sources(sources, dry_run=args.dry_run)

        # Print results
        print()
        print(result.summary())

        # Return appropriate exit code
        if hasattr(result, "videos_failed") and result.videos_failed > 0:
            return 1  # Some videos failed
        return 0

    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(str(e))
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
