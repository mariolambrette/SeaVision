"""SAM 3 (Segment Anything Model 3) detector module."""

from .config import (
    PromptType,
    HybridStrategy,
    PrompterConfig,
    PromptConfig,
    SAM3DetectorConfig,
)
from .detector import SAM3Detector

__all__ = [
    # Config
    "PromptType",
    "HybridStrategy",
    "PrompterConfig",
    "PromptConfig",
    "SAM3DetectorConfig",
    # Detector
    "SAM3Detector",
]