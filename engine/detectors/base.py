"""Base classes for the detectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
        label: Optional class label for the detection.
        track_id: Optional track ID for the detection (if tracking is used).
        mask: Optional Segmentation mask as numpy array (H x W, uint8, 255=object).
        metadata: Optional additional detector-specific data
    """

    source_file: str
    timestamp: float
    frame_number: int
    xc: float
    yc: float
    width: float
    height: float
    confidence: Optional[float] = None
    label: Optional[str] = None
    track_id: Optional[int] = None
    mask: Optional[np.ndarray] = field(default=None, repr=False)
    metadata: Optional[dict] = field(default=None, repr=False)

    def to_csv_row(self) -> dict:
        """Convert the detection to a CSV row string. (dictionary)"""
        row = {
            "source_file": self.source_file,
            "timestamp": f"{self.timestamp:.3f}",
            "frame_number": self.frame_number,
            "xc": f"{self.xc:.1f}",
            "yc": f"{self.yc:.1f}",
            "width": f"{self.width:.1f}",
            "height": f"{self.height:.1f}",
        }
        
        # Add optional fields if present
        if self.confidence is not None:
            row["confidence"] = f"{self.confidence:.3f}"
        else:
            row["confidence"] = ""
            
        if self.label is not None:
            row["label"] = self.label
        else:
            row["label"] = ""
            
        if self.track_id is not None:
            row["track_id"] = str(self.track_id)
        else:
            row["track_id"] = ""
        
        # Note: mask and metadata are not included in CSV
        # (masks should be saved separately if needed)
        
        return row
    
    @property
    def bbox(self) -> tuple:
        """Get bounding box as (x1, y1, x2, y2)."""
        x1 = self.xc - self.width / 2
        y1 = self.yc - self.height / 2
        x2 = self.xc + self.width / 2
        y2 = self.yc + self.height / 2
        return (x1, y1, x2, y2)
    
    @property
    def area(self) -> float:
        """Get area of the bounding box."""
        return self.width * self.height
    
    @classmethod
    def from_bbox(
        cls,
        source_file: str,
        timestamp: float,
        frame_number: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        **kwargs,
    ) -> "Detection":
        """
        Create a Detection from corner-format bounding box.
        
        Args:
            source_file: Path of the source file.
            timestamp: Timestamp in seconds.
            frame_number: Frame index.
            x1, y1: Top-left corner.
            x2, y2: Bottom-right corner.
            **kwargs: Optional fields (confidence, label, track_id, etc.)
        
        Returns:
            Detection with center-format coordinates.
        """
        xc = (x1 + x2) / 2
        yc = (y1 + y2) / 2
        width = x2 - x1
        height = y2 - y1
        
        return cls(
            source_file=source_file,
            timestamp=timestamp,
            frame_number=frame_number,
            xc=xc,
            yc=yc,
            width=width,
            height=height,
            **kwargs,
        )


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