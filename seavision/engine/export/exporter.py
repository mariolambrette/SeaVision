"""
Model Exporter - converts trained YOLO .pt weights to edge format.

This module wraps Ultralytics' export pipeline with SeaVision-specific defaults
and adds export validation. The user interacts with this class; they never need
to call ultralytics.YOLO.export() directly.

Example:
    from seavision.engine.export import ModelExporter, ExportConfig

    config = ExportConfig(
        weights_path="models/fidh_detector.pt",
        output_dir="./deployment",
        imgsz=320,
    )

    exporter = ModelExporter(config)
    result = exporter.export()

    if result.success:
        print(f"Exported to: {result.exported_path}")
        print(f"Model size: {result.model_size_mb:.1f} MB")
        print(f"Classes: {result.class_names}")
    else:
        print(f"Export failed: {result.error}")
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import json

from .config import (
    ExportConfig,
    ExportResult,
    ExportTarget,
    TARGET_EXPORT_INFO,
)
from.validation import validate_export

logger = logging.getLogger(__name__)


class ExportError(Exception):
    """Raised when a model export fails."""
    pass


class ModelExporter:
    """
    Converts trained YOLO .pt weights to edge-optimised formats.

    This class is the dingle entrypoint for model export, It:

    1. Loads the PyTorch model via Ultralytics.
    2. Extracts model metadata (class names, input/output shapes).
    3. Calls Ultralytics export with SeaVision-specific settings.
    4. Optionally validates the export by comparing inference outputs.
    5. Copies the exported artifact to the configured output directory.

    The exporter requires Ultralytics and PyTorch - it runs land-side, not on
    the edge device.
    """

    def __init__(self, config: ExportConfig):
        """
        Initialise the exporter.

        Args:
            config: Export configuration
        """
        self.config = config

    def export(self) -> ExportResult:
        """
        Export the model and return metadata about the result.

        This is the main entrypoint. it handles the full export lifecycle:
        validation of inputs, model loading, export, optional validation, and
        artifact copying.

        Returns:
            ExportResult with success status, exported path, model metadata,
            and validation results.
        """
        config = self.config

        # --- Input validation ---
        weights = Path(config.weights_path)
        if not weights.exists():
            return ExportResult(
                success=False,
                config=config,
                error=f"Weights file not found: {config.weights_path}",
            )
        
        if config.target not in TARGET_EXPORT_INFO:
            return ExportResult(
                success=False,
                config=config,
                error=f"Unsupported export target: {config.target}",
            )
        
        target_info = TARGET_EXPORT_INFO[config.target]
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # --- Load model ---
        try:
            import ultralytics
            logger.info("Loading YOLO model from %S", config.weights_path)
            model = ultralytics.YOLO(config.weights_path)
        except ImportError:
            return ExportResult(
                success=False,
                config=config,
                error=(
                    "Ultralytics is required for model export. "
                    "Install with: pip install ultralytics"
                ),
            )
        except Exception as exc:
            return ExportResult(
                success=False,
                config=config,
                error=f"Failed to load model: {exc}",
            )

        # --- Extract metadata ---
        class_names: Dict[int, str] = {}
        names = getattr(model, "names", None)
        if isinstance(names, dict):
            class_names = {int(k): str(v) for k, v in names.items()}
        elif isinstance(names, (list, tuple)):
            class_names = {i: str(n) for i, n in enumerate(names)}
        
        num_classes = len(class_names) if class_names else 0

        # --- Build export kwargs ---
        export_kwargs = {
            "format": target_info["format"],
            "imgsz": config.imgsz,
            "half": config.half,
            "int8": config.int8,
            "device": config.device,
        }

        if config.target == ExportTarget.ONNX:
            export_kwargs["simplify"] = config.simplify
            export_kwargs["opset"] = config.opset

        # --- Run export ---
        try:
            logger.info(
                "Exporting model to %s (imgsz=%d, half=%s, int8=%s)",
                config.target.name,
                config.imgsz,
                config.half,
                config.int8,
            )
            export_path_raw = model.export(**export_kwargs)

            # Ultralytics returns the path as a string
            export_path = str(export_path_raw)
            logger.info("Ultralytics export completed: %s", export_path)
        except Exception as exc:
            return ExportResult(
                success=False,
                config=config,
                error=f"Export failed: {exc}",
            )

        # --- Copy to output directory ---
        src = Path(export_path)
        suffix = target_info["suffix"]
        dest_name = weights.stem + suffix
        dest = output_dir / dest_name

        try:
            if src.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)

            logger.info("Exported model copied to %s", dest)
        except Exception as exc:
            return ExportResult(
                success=False,
                config=config,
                error=f"Failed to copy exported model to output dir: {exc}",
            )
        
        # --- Compute model size ---
        if dest.is_dir():
            model_size = sum(f.stat().st_size for f in dest.rglob("*"))
        else:
            model_size = dest.stat().st_size
        model_size_mb = model_size / (1024 * 1024)

        # --- Determine input/output shapes ---
        # These come from the ONNX metadata if available, otherwise inferred
        input_shape = [1, 3, config.imgsz, config.imgsz]
        output_shape: List[int] = []

        if config.target == ExportTarget.ONNX:
            try:
                import onnxruntime as ort

                sess = ort.InferenceSession(
                    str(dest), providers=["CPUExecutionProvider"]
                )
                input_shape = list(sess.get_inputs()[0].shape)
                output_shape = list(sess.get_outputs()[0].shape)
            except Exception:
                # Not critical — shapes are informational
                pass

        # --- Validate ---
        validation_result = None
        if config.validate:
            validation_result = validate_export(config, str(dest))

            if not validation_result.passed:
                logger.warning(
                    "Export validation failed. The exported model may "
                    "produce different results than the original. "
                    "Details: %s",
                    validation_result.details,
                )

        # --- Write metadata ---
        # --- Write metadata ---
        self._write_export_metadata(dest, config, class_names, num_classes)

        return ExportResult(
            success=True,
            exported_path=str(dest),
            config=config,
            model_size_mb=round(model_size_mb, 2),
            num_classes=num_classes,
            class_names=class_names,
            input_shape=input_shape,
            output_shape=output_shape,
            validation=validation_result,
        )
    
    def _write_export_metadata(
        self,
        dest: Path,
        config: ExportConfig,
        class_names: Dict[int, str],
        num_classes: int,
    ) -> None:
        """
        Write a JSON metadata file alongside the exported model.

        The metadata file contains everything the edge runtime needs to 
        configure itself: image size, number of classes, class names, and the
        export target. The bundle builder reads this file; the edge runtime
        reads it at startup.
        """
        metadata = {
            "seavision_export_version": 1,
            "source_weights": config.weights_path,
            "target": config.target.name,
            "imgsz": config.imgsz,
            "half": config.half,
            "int8": config.int8,
            "num_classes": num_classes,
            "class_names": class_names,
        }

        # Place metadata next to the model
        if dest.is_dir():
            meta_path = dest / "export_metadata.json"
        else:
            meta_path = dest.with_suffix(".json")

        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Export metadata written to %s", meta_path)