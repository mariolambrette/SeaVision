"""M3B detection package."""

from .source import (
    FrameContext,
    VideoMetadata,
    VideoSource,
    LocalVideoSource,
    S3VideoSource,
    discover_local_videos,
    discover_s3_videos,
)
from .detectors import Detection, DetectorBase
from .postprocessor import (
    OutputMode,
    CSVWriterConfig,
    DetectionWriter,
    FramePostprocessor,
    VideoPostprocessor,
    LabelFilterConfig,
    LabelFilter,
    PerFrameNmsConfig,
    PerFrameNmsPostprocessor,
    MotionTrackVideoConfig,
    MotionTrackVideoPostprocessor,
    PostprocessStage,
    build_postprocess_stages,
)

__all__ = [
    "FrameContext",
    "VideoMetadata", 
    "VideoSource",
    "Detection",
    "DetectorBase",
    "LocalVideoSource",
    "S3VideoSource",
    "discover_local_videos",
    "discover_s3_videos",
    "OutputMode",
    "CSVWriterConfig",
    "DetectionWriter",
    "FramePostprocessor",
    "VideoPostprocessor",
    "LabelFilterConfig",
    "LabelFilter",
    "PerFrameNmsConfig",
    "PerFrameNmsPostprocessor",
    "MotionTrackVideoConfig",
    "MotionTrackVideoPostprocessor",
    "PostprocessStage",
    "build_postprocess_stages",
]
