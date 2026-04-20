"""
Export validation - compare PyTorch and exported model outputs.

Runs a synthetic frame through both models and checks that the exported model
produces detections consistent with the original. This catches silent export
failures where the conversion completes without error but the exported model
behaves differently.
"""

import logging
from pathlib import Path
from typing import List, Tuple, cast

import numpy as np

from .config import ExportConfig, ExportTarget, ValidationResult

logger = logging.getLogger(__name__)


# Thresholds for tensor deviation
MAX_ELEMENT_DEVIATION_THRESHOLD = 0.01
MEAN_ELEMENT_DEVIATION_THRESHOLD = 0.001


def _create_test_frame(imgsz: int) -> np.ndarray:
    """
    Create a synthetic BGR test frame for validation.

    The frame has structured content (gradients, shapes), rather than random 
    noise. This matters because models can behave different on structured vs.
    random input - a model might produce zero detections on noise but produce
    them on structured content, making noise-based validation useless.

    Args:
        imgsz: Image dimension (square).

    Returns:
        A BGR uint8 numpy array of shape (imgsz, imgsz, 3).
    """
    frame = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)

    # Horizontal gradient in blue channel
    frame[:, :, 0] = np.tile(
        np.linspace(0, 255, imgsz, dtype=np.uint8), (imgsz, 1)
    )

    # Vertical gradient in green channel
    frame[:, :, 1] = np.tile(
        np.linspace(0, 255, imgsz, dtype=np.uint8).reshape(-1, 1),
        (1, imgsz),
    )

    # A bright rectangle in the centre (likely to trigger detections)
    quarter = imgsz // 4
    frame[quarter : 3 * quarter, quarter : 3 * quarter] = (200, 200, 200)

    return frame


def _run_pytorch_raw(
    weights_path: str,
    frame: np.ndarray,
    imgsz: int,
    device: str,
) -> np.ndarray:
    """
    Run PyTorch inference and return the raw output tensor.

    Returns the raw model output BEFORE any postprocessing or NMS.
    Shape: [1, 4+num_classes, N] — same layout as the ONNX output.
    """
    import torch
    import ultralytics

    model: ultralytics.YOLO = ultralytics.YOLO(weights_path)

    # Access the underlying PyTorch model to get raw output
    torch_model = model.model

    assert isinstance(torch_model, torch.nn.Module), (
        f"Expected torch.nn.Module, got {type(torch_model)!r}"
    )

    torch_model.eval()

    if device and device != "cpu":
        torch_model = torch_model.to(device)

    # Preprocess identically to the ONNX path
    import cv2
    h, w = frame.shape[:2]
    r = min(imgsz / h, imgsz / w)
    new_w, new_h = int(round(w * r)), int(round(h * r))
    dw = (imgsz - new_w) / 2
    dh = (imgsz - new_h) / 2

    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    top = int(round(dh - 0.1))
    bottom = int(round(dh + 0.1))
    left = int(round(dw - 0.1))
    right = int(round(dw + 0.1))
    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )

    blob = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    blob = blob.astype(np.float32) / 255.0
    blob = np.transpose(blob, (2, 0, 1))
    blob = np.expand_dims(blob, axis=0)

    tensor = torch.from_numpy(blob)
    if device and device != "cpu":
        tensor = tensor.to(device)

    with torch.no_grad():
        output: torch.Tensor = torch_model(tensor)

    # output may be a tuple/list — take the first element
    if isinstance(output, (list, tuple)):
        output = output[0]

    return output.cpu().numpy()


def _run_onnx_raw(
    onnx_path: str,
    frame: np.ndarray,
    imgsz: int,
) -> np.ndarray:
    """
    Run ONNX inference and return the raw output tensor.

    Returns the raw model output BEFORE any postprocessing or NMS.
    Shape: [1, 4+num_classes, N].
    """
    import cv2
    import onnxruntime as ort

    # Preprocess — identical to _run_pytorch_raw above
    h, w = frame.shape[:2]
    r = min(imgsz / h, imgsz / w)
    new_w, new_h = int(round(w * r)), int(round(h * r))
    dw = (imgsz - new_w) / 2
    dh = (imgsz - new_h) / 2

    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    top = int(round(dh - 0.1))
    bottom = int(round(dh + 0.1))
    left = int(round(dw - 0.1))
    right = int(round(dw + 0.1))
    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )

    blob = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    blob = blob.astype(np.float32) / 255.0
    blob = np.transpose(blob, (2, 0, 1))
    blob = np.expand_dims(blob, axis=0)

    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: blob})

    result = output[0]

    if not isinstance(result, np.ndarray):
        raise TypeError(f"Expected numpy.ndarray from ONNX model, got {type(result)!r}")

    return result
    

def _compare_raw_outputs(
    pytorch_output: np.ndarray,
    onnx_output: np.ndarray,
) -> tuple[float, float, bool]:
    """
    Compare raw model output tensors element-wise.

    Returns (max_absolute_deviation, mean_absolute_deviation, shape_match).
    """
    shape_match = pytorch_output.shape == onnx_output.shape

    if not shape_match:
        return float("inf"), float("inf"), False
    
    diff = np.abs(pytorch_output - onnx_output)
    max_dev = float(np.max(diff))
    mean_dev = float(np.mean(diff))

    return max_dev, mean_dev, True


def validate_export(
    config: ExportConfig,
    exported_path: str,
) -> ValidationResult:
    """
    Validate an exported model against the original PyTorch model.

    Runs a synthetic test frame through both models and compares the detection
    outputs. This is the main entry point for export validation.

    Args:
        config: The export configuration (needed for weights_path, imgsz, 
            device, and target).
        exported_path: Path to the exported model file.

    Returns:
        ValidationResult with pass/fail status and deviation metrics.
    """
    logger.info(
        "Validating export: %s vs %s", config.weights_path, exported_path
    )

    frame = _create_test_frame(config.imgsz)

    # Run both models on the same preprocessed input and compare raw outputs
    try:
        pytorch_output = _run_pytorch_raw(
            config.weights_path, frame, config.imgsz, config.device
        )
        logger.info(
            "Pytorch raw output shape: %s", pytorch_output.shape
        )
    except Exception as exc:
        return ValidationResult(
            passed=False,
            details=f"PyTorch inference failed: {exc}",
        )
    
    try:
        if config.target == ExportTarget.ONNX:
            onnx_output = _run_onnx_raw(exported_path, frame, config.imgsz)
            logger.info(
                "ONNX raw output shape: %s", onnx_output.shape
            )
        else:
            # Non-ONNX: file existence check only
            exported_file = Path(exported_path)
            if exported_file.exists():
                size = (
                    sum(f.stat().st_size for f in exported_file.rglob("*"))
                    if exported_file.is_dir()
                    else exported_file.stat().st_size
                )
                if size > 0:
                    return ValidationResult(
                        passed=True,
                        details=(
                            f"File existence check passed for "
                            f"{config.target.name} export ({size / 1e6:.1f} MB). "
                            f"Detailed inference validation is only supported "
                            f"for ONNX exports."
                        ),
                    )
            return ValidationResult(
                passed=False,
                details=f"Exported file not found or empty: {exported_path}",
            )
    except Exception as exc:
        return ValidationResult(
            passed=False,
            details=f"Exported model validation failed: {exc}",
        )

    # Compare raw output tensors
    max_dev, mean_dev, shape_match = _compare_raw_outputs(
        pytorch_output, onnx_output
    )

    if not shape_match:
        return ValidationResult(
            passed=False,
            details=(
                f"Output shape mismatch: PyTorch {pytorch_output.shape} "
                f"vs ONNX {onnx_output.shape}"
            ),
        )
    
    # Thresholds for raw tensor comparison
    passed = (
        max_dev < MAX_ELEMENT_DEVIATION_THRESHOLD 
        and mean_dev < MEAN_ELEMENT_DEVIATION_THRESHOLD
    )

    details_parts = [
        f"Output_shape: {pytorch_output.shape}",
        f"Max element deviation: {max_dev:.6f}",
        f"Mean element deviation: {mean_dev:.6f}",
    ]

    if not passed:
        details_parts.append(
            f"FAIL: Deviations exceed tolerace (max > "
            f"{MAX_ELEMENT_DEVIATION_THRESHOLD} or mean > "
            f"{MEAN_ELEMENT_DEVIATION_THRESHOLD})"
        )

    result = ValidationResult(
        passed=passed,
        max_box_deviation=max_dev,
        max_confidence_deviation=mean_dev,
        details="; ".join(details_parts),
    )

    if passed:
        logger.info("Export validation PASSED: %s", result.details)
    else:
        logger.warning("Export validation FAILED: %s", result.details)

    return result