"""
YOLO-based object detector for SeaVision.

This package provides:
- YOLODetectorConfig: configuration for the YOLO detector.
- YOLODetector: DetectorBase-compatible wrapper around Ultralytics YOLO.
"""

from .config import YOLODetectorConfig
from .detector import YOLODetector

__all__ = ["YOLODetector", "YOLODetectorConfig"]
