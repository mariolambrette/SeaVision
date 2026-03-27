"""Base classes for video source handling."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Tuple
import numpy as np


@dataclass
class VideoMetadata:
    """
    Metadata for a video source.

    Attributes:
        source_file: Path of the original source file.
        fps: Frames per second of the video.
        frame_count: Total number of frames in the video.
        width: Width of the video frames (pixels).
        height: Height of the video frames (pixels).
        duration: Duration of the video (seconds).
    """
    source_file: str
    fps: float
    frame_count: int
    width: int
    height: int
    duration: float


@dataclass
class FrameContext:
    """Context information passed with each frame to detectors.
    
    Attributes:
        source_file: Path or identifier of the source video.
        frame_number: Frame index within the video.
        timestamp: Timestamp within the video (seconds from start).
        fps: Frames per second of the source video.
    """
    source_file: str
    frame_number: int
    timestamp: float
    fps: float


class VideoSource(ABC):
    """Abstract base class for video sources.
    
    Provides a common interface for loading video frames from different
    backends (local files, S3, etc.).
    """
    
    @abstractmethod
    def iter_frames(self) -> Iterator[Tuple[np.ndarray, FrameContext]]:
        """Iterate over frames in the video.
        
        Yields:
            Tuple of (frame, context) where frame is a BGR numpy array
            and context contains metadata about the frame.
        """
        pass
    
    @abstractmethod
    def get_metadata(self) -> VideoMetadata:
        """Get metadata about the video source.
        
        Returns:
            VideoMetadata object with file information.
        """
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - performs cleanup."""
        self.close()
        return False
    
    def close(self) -> None:
        """Release any resources held by the source.
        
        Override this method if your source needs cleanup
        (e.g., closing file handles, network connections).
        """
        pass
