"""
CLI entry point for model export and edge bundle creation.

Usage:
    seavision-export --weights models/fish.pt --output ./deployment
    seavision-export --weights models/fish.pt --imgsz 320 --target onnx
"""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="seavision-export",
        description="Export a trained YOLO model for edge deployment",
    )

    parser.add_argument(
        "--weights", required=True,
        help="Path to the trained .pt weights file",
    )
    parser.add_argument(
        "--output", default="./export",
        help="Output directory for exported model and bundle (default: ./export)",
    )
    parser.add_argument(
        "--target", default="onnx",
        choices=["onnx", "tflite", "ncnn", "torchscript"],
        help="Export target format (default: onnx)",
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Input image size (default: 640)",
    )
    parser.add_argument(
        "--half", action="store_true",
        help="Use float16 quantisation",
    )
    parser.add_argument(
        "--int8", action="store_true",
        help="Use int8 quantisation",
    )
    parser.add_argument(
        "--no-validate", action="store_true",
        help="Skip export validation",
    )
    parser.add_argument(
        "--no-bundle", action="store_true",
        help="Export only — do not create deployment bundle",
    )
    parser.add_argument(
        "--device", default="cpu",
        help="Device for export (default: cpu)",
    )
    parser.add_argument(
        "--conf", type=float, default=0.25,
        help="Default confidence threshold for edge config (default: 0.25)",
    )
    parser.add_argument(
        "--frame-skip", type=int, default=1,
        help="Default frame skip for edge config (default: 1)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from seavision.engine.export import (
        ExportConfig,
        ExportTarget,
        ModelExporter,
    )

    # Map string target to enum
    target_map = {
        "onnx": ExportTarget.ONNX,
        "tflite": ExportTarget.TFLITE,
        "ncnn": ExportTarget.NCNN,
        "torchscript": ExportTarget.TORCHSCRIPT,
    }

    config = ExportConfig(
        weights_path=args.weights,
        output_dir=args.output,
        target=target_map[args.target],
        imgsz=args.imgsz,
        half=args.half,
        int8=args.int8,
        validate=not args.no_validate,
        device=args.device,
    )

    # --- Export ---
    print(f"Exporting {args.weights} to {args.target.upper()}...")
    exporter = ModelExporter(config)
    result = exporter.export()

    if not result.success:
        print(f"\nERROR: Export failed: {result.error}")
        return 1

    print(f"\nExport successful:")
    print(f"  Model: {result.exported_path}")
    print(f"  Size:  {result.model_size_mb:.1f} MB")
    print(f"  Classes: {result.num_classes}")
    if result.class_names:
        names = ", ".join(
            f"{k}={v}" for k, v in sorted(result.class_names.items())[:10]
        )
        if len(result.class_names) > 10:
            names += f", ... ({len(result.class_names)} total)"
        print(f"  Labels: {names}")

    if result.validation:
        status = "PASSED" if result.validation.passed else "FAILED"
        print(f"  Validation: {status}")
        print(f"    {result.validation.details}")

    # --- Bundle ---
    if not args.no_bundle:
        from pathlib import Path
        from seavision.edge.bundle import BundleBuilder
        from seavision.edge.config import EdgeConfig

        # Find the metadata file
        exported_path = Path(result.exported_path)
        if exported_path.is_dir():
            metadata_path = exported_path / "export_metadata.json"
        else:
            metadata_path = exported_path.with_suffix(".json")

        if not metadata_path.exists():
            print(f"\nWARNING: Metadata file not found at {metadata_path}")
            print("Skipping bundle creation.")
            return 0

        # Create edge config with CLI overrides
        edge_config = EdgeConfig(
            conf_threshold=args.conf,
            frame_skip=args.frame_skip,
        )

        bundle_dir = Path(args.output) / "bundle"
        print(f"\nCreating deployment bundle: {bundle_dir}")

        builder = BundleBuilder(
            exported_model_path=result.exported_path,
            export_metadata_path=str(metadata_path),
            output_dir=str(bundle_dir),
            edge_config=edge_config,
        )
        bundle_path = builder.build()

        print(f"\nBundle created: {bundle_path}")
        print(f"\nDeployment instructions:")
        print(f"  1. Copy the '{bundle_dir.name}' directory to your Pi:")
        print(f"     scp -r {bundle_dir} pi@<pi-ip>:~/")
        print(f"  2. On the Pi:")
        print(f"     cd ~/{bundle_dir.name}")
        print(f"     chmod +x install.sh")
        print(f"     ./install.sh")
        print(f"  3. Run the detector:")
        print(f"     python3 run.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
