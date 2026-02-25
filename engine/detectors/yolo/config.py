"""Configuration dataclass for the YOLO detector."""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class YOLODetectorConfig:
    """
    Configuration for the YOLO detector.

    Attributes:
        model_path: Path to the YOLO model weights.
        device: Device to run the model on (e.g., 'cpu', 'cuda', or 'mps').
        imgsz: Inference image size (e.g., 640), passed to the YOLO model.
        conf_threshold: Minimum confidence score for detections.
        iou_threshold: IoU threshold for non-max suppression.
        max_detections: Maximum number of detections per image.
        classes: Optional list of class indices to keep. If None, keep all
            classes.
        output_labels: Whether to map class indicies to human-readable labels
            using the model's built-in names.
        half: Whether to use half precision (float16) for inference. Only
            applicable on compatible devices (e.g., CUDA).
        verbose: Whether to print detailed logs during inference (default True).
    """

    model_path: str = ""
    device: str = "cpu"
    imgsz: int = 640

    conf_threshold: float = 0.25
    iou_threshold: float = 0.45
    max_detections: int = 300

    classes: Optional[List[int]] = None
    output_labels: bool = True

    half: bool = False
    verbose: bool = True
