"""Detection data structures and detector interface.

Base classes (Detection, DetectorBase) are imported eagerly.
Optional detector implementations (SAM3, YOLO) use lazy imports
to avoid pulling in torch/ultralytics at package initialisation time.
This allows lightweight consumers (like the GUI) to import Detection
without triggering heavy dependency loads.
"""

from .base import Detection, DetectorBase

__all__ = ["Detection", "DetectorBase"]

# Lazy-loaded flags — None means "not yet checked"
_SAM3_AVAILABLE = None
_YOLO_AVAILABLE = None

# Names that trigger lazy loading when accessed
_SAM3_NAMES = frozenset({
    "SAM3Detector", "SAM3DetectorConfig", "PromptType",
    "HybridStrategy", "PrompterConfig", "PromptConfig",
    "SAM3_AVAILABLE",
})
_YOLO_NAMES = frozenset({
    "YOLODetector", "YOLODetectorConfig",
    "YOLO_AVAILABLE",
})


def __getattr__(name):
    """Lazy import for optional detector implementations."""
    global _SAM3_AVAILABLE, _YOLO_AVAILABLE

    if name in _SAM3_NAMES:
        if _SAM3_AVAILABLE is None:
            try:
                from .sam3 import (
                    SAM3Detector,
                    SAM3DetectorConfig,
                    PromptType,
                    HybridStrategy,
                    PrompterConfig,
                    PromptConfig,
                )
                _SAM3_AVAILABLE = True
                # Inject into module namespace so subsequent access is fast
                globals().update({
                    "SAM3Detector": SAM3Detector,
                    "SAM3DetectorConfig": SAM3DetectorConfig,
                    "PromptType": PromptType,
                    "HybridStrategy": HybridStrategy,
                    "PrompterConfig": PrompterConfig,
                    "PromptConfig": PromptConfig,
                    "SAM3_AVAILABLE": True,
                })
            except Exception:
                _SAM3_AVAILABLE = False
                globals()["SAM3_AVAILABLE"] = False

        if name == "SAM3_AVAILABLE":
            return _SAM3_AVAILABLE
        if not _SAM3_AVAILABLE:
            raise ImportError(
                f"{name} is not available (SAM3 dependencies not installed)"
            )
        return globals()[name]

    if name in _YOLO_NAMES:
        if _YOLO_AVAILABLE is None:
            try:
                from .yolo import YOLODetector, YOLODetectorConfig
                _YOLO_AVAILABLE = True
                globals().update({
                    "YOLODetector": YOLODetector,
                    "YOLODetectorConfig": YOLODetectorConfig,
                    "YOLO_AVAILABLE": True,
                })
            except Exception:
                _YOLO_AVAILABLE = False
                globals()["YOLO_AVAILABLE"] = False

        if name == "YOLO_AVAILABLE":
            return _YOLO_AVAILABLE
        if not _YOLO_AVAILABLE:
            raise ImportError(
                f"{name} is not available (YOLO dependencies not installed)"
            )
        return globals()[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
