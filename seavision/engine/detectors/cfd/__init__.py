"""Community Fish Detector (CFD) detector for SeaVision.

Provides:
- CFDDetectorConfig: configuration for the CFD detector.
- CFDDetector: DetectorBase-compatible wrapper around the CFD RF-DETR models.
"""

from .config import CFDDetectorConfig
from .detector import CFDDetector

__all__ = ["CFDDetector", "CFDDetectorConfig"]
