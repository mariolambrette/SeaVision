"""
Bundle builder — packages model + runtime for edge deployment.

Creates a self-contained directory with everything needed to run
inference on a Raspberry Pi or similar ARM device:

    my_deployment/
    ├── model.onnx               # Exported model
    ├── config.json              # EdgeConfig, pre-populated
    ├── run.py                   # Single-file entry point
    ├── seavision_edge/          # Copied edge runtime package
    │   ├── __init__.py
    │   ├── config.py
    │   ├── runtime.py
    │   ├── capture.py
    │   ├── writer.py
    │   └── postprocess.py
    ├── requirements.txt         # Minimal pip dependencies
    ├── install.sh               # Setup script for the Pi
    └── export_metadata.json     # Model metadata from export
"""

import json
import logging
import shutil
import textwrap
from pathlib import Path
from typing import Optional

from .config import EdgeConfig

logger = logging.getLogger(__name__)


class BundleBuilder:
    """
    Packages and exported model and edge runtime into a deployment bundle.

    The bundle is a directory containing the model, a pre-populated config file,
    a standalone entry-point script, a copy of the edge runtime package, and a
    setup script. The user copies the bundle to the Pi and runs install.sh

    The edge runtime files are copied into the bundle so that the user does NOT
    need to install the full SeaVision package on the edge device.
    """

    def __init__(
        self,
        exported_model_path: str,
        export_metadata_path: str,
        output_dir: str = "./bundle",
        edge_config: Optional[EdgeConfig] = None,
    ):
        """
        Initialise the builder.

        Args:
            exported_model_path: Path to the exported model file (e.g.
                model.onnx).
            export_metadata_path: Path to the export_metadata.json file
                written by ModelExporter.
            output_dir: Directory to create the bundle in.
            edge_config: Optional pre-configured EdgeConfig. If None,
                defaults are populated from the export metadata.
        """
        self.exported_model_path = Path(exported_model_path)
        self.export_metadata_path = Path(export_metadata_path)
        self.output_dir = Path(output_dir)
        self.edge_config = edge_config

    def build(self) -> str:
        """
        Build the deployment bundle.

        Returns:
            Path to the bundle directory.

        Raises:
            FileNotFoundError: If the model or metadata file is missing.
        """
        if not self.exported_model_path.exists():
            raise FileNotFoundError(
                f"Exported model not found: {self.exported_model_path}"
            )
        if not self.export_metadata_path.exists():
            raise FileNotFoundError(
                f"Export metadata not found: {self.export_metadata_path}"
            )

        # Load export metadata
        with open(self.export_metadata_path, "r") as f:
            metadata = json.load(f)

        # Create bundle directory
        bundle_dir = self.output_dir
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # --- 1. Copy model ---
        model_dest = bundle_dir / self.exported_model_path.name
        if self.exported_model_path.is_dir():
            if model_dest.exists():
                shutil.rmtree(model_dest)
            shutil.copytree(self.exported_model_path, model_dest)
        else:
            shutil.copy2(self.exported_model_path, model_dest)
        logger.info("Copied model to bundle: %s", model_dest.name)

        # --- 2. Copy metadata ---
        shutil.copy2(
            self.export_metadata_path, bundle_dir / "export_metadata.json"
        )

        # --- 3. Copy edge runtime package into the bundle ---
        self._copy_edge_package(bundle_dir)

        # --- 4. Build and write EdgeConfig ---
        config = self._build_edge_config(metadata, model_dest.name)
        config.to_file(str(bundle_dir / "config.json"))

        # --- 5. Write run.py ---
        self._write_run_script(bundle_dir)

        # --- 6. Write requirements.txt ---
        self._write_requirements(bundle_dir)

        # --- 7. Write install.sh ---
        self._write_install_script(bundle_dir)

        logger.info("Bundle created: %s", bundle_dir)
        return str(bundle_dir)
    
    def _copy_edge_package(self, bundle_dir: Path) -> None:
        """
        Copy the seavision.edge package into the bundle.

        This makes the bundle self-contained - the Pi does not need the full
        seavision package installed. The files are placed in a directory called
        ``seavision_edge/`` so they are importable as a top-level package
        wihtout conflicting with an installed ``seavision`` package.
        """
        import seavision.edge as edge_pkg

        edge_src = Path(edge_pkg.__file__).parent
        edge_dest = bundle_dir / "seavision_edge"

        if edge_dest.exists():
            shutil.rmtree(edge_dest)

        edge_dest.mkdir()

        # Copy only .py files
        for py_file in edge_src.glob("*.py"):
            shutil.copy2(py_file, edge_dest / py_file.name)

        # Write a minimal __init__.py for the copied package that
        # imports eagerly (onnxruntime WILL be installed on the Pi).
        init_content = textwrap.dedent('''\
            """SeaVision edge runtime (bundled copy)."""
            from .config import EdgeConfig
            from .runtime import EdgeRuntime

            __all__ = ["EdgeConfig", "EdgeRuntime"]
        ''')
        (edge_dest / "__init__.py").write_text(init_content, encoding="utf-8")

        logger.info("Edge runtime copied to bundle: %s", edge_dest.name)

    def _build_edge_config(
        self,
        metadata: dict,
        model_filename: str,
    ) -> EdgeConfig:
        """
        Build an EdgeConfig from export metadata, overriding with any
        user-provided config values.
        """
        # Start from user config or defaults
        config = self.edge_config or EdgeConfig()

        # Override with export metadata (these must match the export)
        config.model_path = model_filename
        config.imgsz = metadata.get("imgsz", config.imgsz)
        config.num_classes = metadata.get("num_classes", config.num_classes)

        class_names_raw = metadata.get("class_names", {})
        config.class_names = {int(k): v for k, v in class_names_raw.items()}

        return config
    
    def _write_run_script(self, bundle_dir: Path) -> None:
        """
        Write the standalone entry-point script.

        The script imports from the bundled ``seavision_edge/`` package
        first (which is always present in the bundle directory). If that
        fails for some reason, it falls back to the installed
        ``seavision.edge`` package.
        """
        script = textwrap.dedent('''\
            #!/usr/bin/env python3
            """
            SeaVision Edge Runtime — standalone entry point.

            Usage:
                python run.py                      # Use config.json defaults
                python run.py --config myconfig.json
                python run.py --source 0            # Camera 0
                python run.py --source video.mp4    # Video file
            """

            import argparse
            import os
            import sys


            def main():
                parser = argparse.ArgumentParser(
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
                    help="Override frame skip (process every Nth frame)",
                )
                args = parser.parse_args()

                # Ensure the bundle directory is on sys.path so the
                # bundled seavision_edge/ package is importable.
                script_dir = os.path.dirname(os.path.abspath(__file__))
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)

                # Try the bundled copy first, then the installed package.
                try:
                    from seavision_edge import EdgeConfig, EdgeRuntime
                except ImportError:
                    try:
                        from seavision.edge import EdgeConfig, EdgeRuntime
                    except ImportError:
                        print(
                            "ERROR: Cannot find the SeaVision edge runtime.\\n"
                            "Ensure the seavision_edge/ directory is present "
                            "in the bundle directory, or install the seavision "
                            "package."
                        )
                        sys.exit(1)

                # Load config
                try:
                    config = EdgeConfig.from_file(args.config)
                except FileNotFoundError:
                    print(f"ERROR: Config file not found: {args.config}")
                    sys.exit(1)

                # Apply CLI overrides
                if args.source is not None:
                    config.source = args.source
                if args.conf is not None:
                    config.conf_threshold = args.conf
                if args.frame_skip is not None:
                    config.frame_skip = args.frame_skip

                # Run
                runtime = EdgeRuntime(config)
                runtime.run()


            if __name__ == "__main__":
                main()
        ''')

        script_path = bundle_dir / "run.py"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        # Make executable on Unix
        script_path.chmod(0o755)

        logger.info("Entry point written: %s", script_path.name)

    def _write_requirements(self, bundle_dir: Path) -> None:
        """Write the minimal requirements.txt for the edge device."""
        requirements = textwrap.dedent("""\
            # SeaVision Edge Runtime — minimal dependencies
            # Tested on Raspberry Pi 4 (64-bit OS, aarch64)
            #
            # IMPORTANT: numpy 2.0+ causes "Illegal instruction" crashes
            # on Pi 4 (Cortex-A72 / ARMv8.0). Pin to < 2.0.
            numpy<2.0
            opencv-python-headless
            onnxruntime
        """)

        with open(bundle_dir / "requirements.txt", "w", encoding="utf-8") as f:
            f.write(requirements)

    def _write_install_script(self, bundle_dir: Path) -> None:
        """Write the Pi-side installation script."""
        script = textwrap.dedent("""\
            #!/bin/bash
            # SeaVision Edge Runtime — Installation Script
            #
            # Run this on the Raspberry Pi after copying the bundle:
            #   chmod +x install.sh
            #   ./install.sh
            #
            # Prerequisites:
            #   - Python 3.10+ (64-bit)
            #   - pip

            set -e

            echo "========================================"
            echo " SeaVision Edge Runtime — Setup"
            echo "========================================"

            SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
            cd "$SCRIPT_DIR"

            # --- Check Python version ---
            PYTHON=${PYTHON:-python3}
            PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            echo "Python: $PYTHON ($PY_VERSION)"

            # --- Install dependencies ---
            echo ""
            echo "[1/3] Installing Python dependencies..."
            $PYTHON -m pip install --upgrade pip
            $PYTHON -m pip install -r requirements.txt

            # --- Verify ---
            echo ""
            echo "[2/3] Verifying installation..."
            $PYTHON -c "
            import numpy
            import cv2
            import onnxruntime as ort
            print(f'  numpy:       {numpy.__version__}')
            print(f'  opencv:      {cv2.__version__}')
            print(f'  onnxruntime: {ort.__version__}')
            print(f'  providers:   {ort.get_available_providers()}')
            print()
            print('  All dependencies OK!')
            "

            # --- Optional: systemd service ---
            echo ""
            echo "[3/3] Systemd service (optional)"
            echo ""
            echo "To run the detector as a system service that starts on boot:"
            echo ""
            echo "  sudo tee /etc/systemd/system/seavision-edge.service << EOF"
            echo "  [Unit]"
            echo "  Description=SeaVision Edge Detector"
            echo "  After=network.target"
            echo ""
            echo "  [Service]"
            echo "  Type=simple"
            echo "  User=$USER"
            echo "  WorkingDirectory=$SCRIPT_DIR"
            echo "  ExecStart=$PYTHON $SCRIPT_DIR/run.py"
            echo "  Restart=on-failure"
            echo "  RestartSec=10"
            echo ""
            echo "  [Install]"
            echo "  WantedBy=multi-user.target"
            echo "  EOF"
            echo ""
            echo "  sudo systemctl daemon-reload"
            echo "  sudo systemctl enable seavision-edge"
            echo "  sudo systemctl start seavision-edge"
            echo ""

            echo "========================================"
            echo " Setup complete!"
            echo ""
            echo " To run manually:"
            echo "   $PYTHON run.py"
            echo ""
            echo " To run on a video file:"
            echo "   $PYTHON run.py --source /path/to/video.mp4"
            echo "========================================"
        """)

        script_path = bundle_dir / "install.sh"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        script_path.chmod(0o755)
        logger.info("Install script written: %s", script_path.name)