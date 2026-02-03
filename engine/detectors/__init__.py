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