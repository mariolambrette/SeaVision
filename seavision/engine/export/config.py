"""Configuration and result types for model exprt to edge formats."""

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional


class ExportTarget(Enum):
    """
    Supported export target formats.
    
    Each target produces a different model artifact optimised for a specific
    runtime or hardware accelerator.
    """

    ONNX = auto()        # ONNX Runtime - best for Raspberry Pi CPU
    TFLITE = auto()      # TensorFlow Lite - required for Coral Edge TPU
    NCNN = auto()        # Tencent ncnn - lightweight, no runtime dependency
    TORCHSCRIPT = auto() # Torchhscript - fallback requires PyTorch on device


# Maps Export Target to the Ultralytics export format string and the file
# extension (or directory suffix) of the resulting artifact.
TARGET_EXPORT_INFO: Dict[ExportTarget, Dict[str, str]] = {
    ExportTarget.ONNX: {
        "format": "onnx",
        "suffix": ".onnx",
        "runtime_package": "onnxruntime",
    },
    ExportTarget.TFLITE: {
        "format": "tflite",
        "suffix": ".tflite",
        "runtime_package": "tflite-runtime",
    },
    ExportTarget.NCNN: {
        "format": "ncnn",
        "suffix": "_ncnn_model",
        "runtime_package": "ncnn",
    },
    ExportTarget.TORCHSCRIPT: {
        "format": "torchscript",
        "suffix": ".torchscript",
        "runtime_package": "torch",
    },
}


@dataclass
class ExportConfig:
    """
    Configuration for exporting a trained YOLO model to an edge format.
    
    Attributes:
        weights_path: Path to the trained .pt weights file. Must exist.
        output_dir: Directory to write the exported model and metadata. Created
            if it does not exist.
        target: Export target format. Determines which runtime is needed on the
            edge device and which optimisations are applied. Default is ONNX -
            the most reliable and best-performaing options for Raspberry Pi
            4/5 CPU inference.
        imgsz: Input image size for the exported model. The edge runtime must
            use the same size. Smaller sizes (320) run faster but detect fewer
            small objects. Larger sizes (640) are the more accurate but slower.
            This is hte single most impactful performance knob for edge 
            deployment.
        half: Use float16 quanitisation. Reduces model size by ~50% with minimal
            accuracy loss on most detection tasks. Not supported on all targets
            or devices - ONNX on ARM CPUs does not benefit from half precision,
            so this defaults to False.
        int8: Use int8 quantisation. Aggressive size and speed optimisation. May
            impact detection accuracy, especially for small or low-contrast
            objects. Requires a calibration dataset for TFLite exports.
        simplify: Run ONNX graph simplification passes. Folds constants,
            eliminates dead nodes, and merges operations. Reccommended for all
            edge deployments - the simplified graph runs faster and is smaller.
            Only applies to ONNX target.
        opset: ONNX opset version. Higher opsets support more operations but may
            not be supported by older ONNX Runtime versions. Default 12 is
            widely compatible. Only applies to ONNX target.
        validate: Run export validation after conversion. Loads both the
            original PyTorch model and the exported model, runs a synthetic
            frame through each, and ocmpares outputs. Catches silent export
            failures where the conversion completes without error but produces
            different detections.
        device: Device to use for the PyTorch model during export and
            validation. Use 'cpu' unless you have a CUDA GPU available, in which
            case 'cuda' will speed up the export process.
    """

    weights_path: str = ""
    output_dir: str = "./export"

    target: ExportTarget = ExportTarget.ONNX
    imgsz: int = 640
    half: bool = False
    int8: bool = False
    simplify: bool = True
    opset: int = 12

    validate: bool = True
    device: str = "cpu"


@dataclass
class ValidationResult:
    """Result of comparing PyTorch vs exported model outputs.

    Attributes:
        passed: Whether the validation passed — the exported model
            produces detections consistent with the PyTorch original.
        num_detections_pytorch: Number of detections from the PyTorch model.
        num_detections_exported: Number of detections from the exported model.
        max_box_deviation: Maximum pixel deviation between matched boxes.
            A value under 2.0 pixels is normal and caused by floating
            point differences between runtimes.
        max_confidence_deviation: Maximum confidence score deviation
            between matched detections.
        details: Human-readable summary of the comparison.
    """

    passed: bool = False
    num_detections_pytorch: int = 0
    num_detections_exported: int = 0
    max_box_deviation: float = 0.0
    max_confidence_deviation: float = 0.0
    details: str = ""


@dataclass
class ExportResult:
    """Result of a model export operation.

    Returned by ModelExporter.export(). Contains everything the bundle
    builder needs to package the model for deployment.

    Attributes:
        success: Whether the export completed without error.
        exported_path: Path to the exported model file or directory.
        config: The ExportConfig that was used.
        model_size_mb: Size of the exported model in megabytes.
        num_classes: Number of detection classes in the model.
        class_names: Mapping of class index to human-readable name,
            extracted from the YOLO model's metadata.
        input_shape: Expected input tensor shape, e.g. [1, 3, 640, 640].
        output_shape: Output tensor shape, e.g. [1, 84, 8400].
        validation: Validation result, if validation was enabled.
        error: Error message if the export failed.
    """

    success: bool = False
    exported_path: str = ""
    config: Optional[ExportConfig] = None
    model_size_mb: float = 0.0
    num_classes: int = 0
    class_names: Dict[int, str] = field(default_factory=dict)
    input_shape: List[int] = field(default_factory=list)
    output_shape: List[int] = field(default_factory=list)
    validation: Optional[ValidationResult] = None
    error: str = ""
