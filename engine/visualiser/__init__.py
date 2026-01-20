"""Visualiser module for detection overlay on video."""

from engine.visualiser.config import (
    OutputMode,
    LabelPosition,
    BoundingBoxStyle,
    LabelStyle,
    OverlayStyle,
    VideoOutputConfig,
    VisualiserConfig
)
from engine.visualiser.annotator import FrameAnnotator
from engine.visualiser.writer import (
    VideoWriterHandle,
    OutputNameFunction,
    extract_output_stem,
    sanitise_filename
)
from engine.visualiser.loader import (
    DetectionSource,
    FrameDetections,
    CSVDetectionLoader,
    IteratorDetectionSource,
    ListDetectionSource,
    load_detections_from_csv,
)
from engine.visualiser.visualiser import (
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
