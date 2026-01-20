"""Base classes for the detectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, Optional
import numpy as np
from engine.source import FrameContext

@dataclass
class Detection:
    """
    Represents a single detection in a video frame.
    
    Attributes:
        source_file: Path of the original source file.
        timestamp: Timestamp within the video (seconds from the start).
        frame_number: Frame index within the video.
        xc: X coordinate of the detection center (pixels).
        yc: Y coordinate of the detection center (pixels).
        width: Width of the detection bounding box (pixels).
        height: Height of the detection bounding box (pixels).
        confidence: Confidence score of the detection (0.0 to 1.0), or None
            if not applicable.
    """

    source_file: str
    timestamp: float
    frame_number: int
    xc: float
    yc: float
    width: float
    height: float
    confidence: Optional[float] = None

    def to_csv_row(self) -> dict:
        """Convert the detection to a CSV row string. (dictionary)"""
        return {
            "source_file": self.source_file,
            "timestamp": f"{self.timestamp:.3f}",
            "frame_number": self.frame_number,
            "xc": f"{self.xc:.1f}",
            "yc": f"{self.yc:.1f}",
            "width": f"{self.width:.1f}",
            "height": f"{self.height:.1f}",
            "confidence": f"{self.confidence:.3f}" if self.confidence is not None else "",
        }


class DetectorBase(ABC):
    """
    Abstract base class for all detectors.

    Subclasses must implement the `process_frame` method to analyse individual
    frame and yield detections.

    The detector maintains internal state between frames (e.g. background 
    models, tracking state) and should be reset between video files.
    """

    @abstractmethod
    def process_frame(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process a single video frame and yield detections.

        Args:
            frame: BGR image as a numpy array (H x W x 3).
            context: Metadata about the current frame (FrameContext class).

        Yields:
            Detection objects for each candidate found in the frame.
        """
        pass

    def reset(self) -> None:
        """
        Reset detector state for a new video file.
        
        Override this method if your detector maintains state that should be
        cleared between video files (e.g. background models, trackers).
        The default implementation does nothing.
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - performs cleanup."""
        self.reset()
        return False