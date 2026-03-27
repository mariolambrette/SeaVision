"""Visualiser module for detection overlay on video."""

from .config import (
    OutputMode,
    LabelPosition,
    BoundingBoxStyle,
    LabelStyle,
    OverlayStyle,
    VideoOutputConfig,
    VisualiserConfig
)
from .annotator import FrameAnnotator
from .writer import (
    VideoWriterHandle,
    OutputNameFunction,
    extract_output_stem,
    sanitise_filename
)
from .loader import (
    DetectionSource,
    FrameDetections,
    CSVDetectionLoader,
    IteratorDetectionSource,
    ListDetectionSource,
    load_detections_from_csv,
)
from .visualiser import (
    AnnotatedFrame,
    VisualisationResult,
    LiveVisualiser,
    PostHocVisualiser
)

__all__ = [
    # Config
    "OutputMode",
    "LabelPosition", 
    "BoundingBoxStyle",
    "LabelStyle",
    "OverlayStyle",
    "VideoOutputConfig",
    "VisualiserConfig",
    # Writer utilities
    "VideoWriterHandle",
    "OutputNameFunction",
    "extract_output_stem",
    "sanitise_filename",
    # Annotator
    "FrameAnnotator",
    # Loaders
    "DetectionSource",
    "FrameDetections",
    "CSVDetectionLoader",
    "IteratorDetectionSource",
    "ListDetectionSource",
    "load_detections_from_csv",
    # Visualisers
    "AnnotatedFrame",
    "VisualisationResult",
    "LiveVisualiser",
    "PostHocVisualiser",
]
