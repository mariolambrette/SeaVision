"""Detection data structures and detector interface."""

from .base import Detection, DetectorBase

# Conditional imports for optional detectors
__all__ = ["Detection", "DetectorBase"]

# SAM 3 - requires ultralytics
try:
    from .sam3 import (
        SAM3Detector,
        SAM3DetectorConfig,
        PromptType,
        HybridStrategy,
        PrompterConfig,
        PromptConfig,
    )
    __all__.extend([
        "SAM3Detector",
        "SAM3DetectorConfig",
        "PromptType",
        "HybridStrategy",
        "PrompterConfig",
        "PromptConfig",
    ])
    SAM3_AVAILABLE = True
except ImportError:
    SAM3_AVAILABLE = False

# YOLO - requires ultralytics
try:
    from .yolo import YOLODetector, YOLODetectorConfig

    __all__.extend([
        "YOLODetector",
        "YOLODetectorConfig",
    ])
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False