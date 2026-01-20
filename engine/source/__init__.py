"""Video source handling."""

from .base import FrameContext, VideoMetadata, VideoSource
from .local import LocalVideoSource
from .s3 import S3VideoSource
from .discovery import discover_local_videos, discover_s3_videos

__all__ = [
    "FrameContext", 
    "VideoMetadata",
    "VideoSource", 
    "LocalVideoSource",
    "S3VideoSource",
    "discover_local_videos",
    "discover_s3_videos",
]
