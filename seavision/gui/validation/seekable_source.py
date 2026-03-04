"""Random access video source for the GUI viewer."""

import cv2
import numpy as np
from pathlib import Path


from seavision.engine.source.base import FrameContext, VideoMetadata

class SeekableVideoSource:
    """
    Random-access wrapper around cv2.VideoCapture.

    Unlike LocalVideoSource (which iterates sequentially), this class supports
    seeking to arbitrary frame numbers. Designed for the GUI viewer where the
    user may jump around in the video timeline.

    Compatible only with local video files, not live network streams.

    Usage:
        with SeekableVideoSource("video.ts") as src:
            frame, ctx = src.read_at(47)
            frame, ctx = src.read_at(183)
    """

    def __init__(self, filepath: str) -> None:
        self._filepath = filepath
        self._cap = cv2.VideoCapture(filepath)

        if not Path(self._filepath).exists():
            raise ValueError(f"Video file not found: {filepath}")

        if not self._cap.isOpened():
            raise ValueError(f"Failed to open video file: {filepath}")
        
        self._metadata = self._read_metadata()

    
    def _read_metadata(self) -> VideoMetadata:
        """Read and cache the video metadata from the capture."""

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0.0

        return VideoMetadata(
            source_file=self._filepath,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            duration=duration
        )
    
    @property
    def metadata(self) -> VideoMetadata:
        """Cached video metadata."""
        return self._metadata
    
    def seek(self, frame_number: int) -> None:
        """
        Seek to a specific frame number.

        The frame number is clamped to the valid range. This prevents invalid
        frames being read causing hidden failures.
        
        In .ts files, seek accuracy may be off by 1-2 frames due to keyframe 
        alignment.
        """
        clamped = max(0, min(frame_number, self._metadata.frame_count - 1))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, clamped)

    def read(self) -> tuple[np.ndarray, FrameContext] | None:
        """
        Read the current frame and advance the position.

        returns:
            Tuple of (frame, context) or None if at the end of the video or the
            frame could not be decoded.
        """
        ret, frame = self._cap.read()
        if not ret:
            return None
        
        # CAP_PROP_POS_FRAMES gives the NEXT frame to be read, so the currently
        # read frame is at position - 1
        pos = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        timestamp = pos / self._metadata.fps if self._metadata.fps > 0 else 0.0

        context = FrameContext(
            source_file=self._filepath,
            frame_number=pos,
            timestamp=timestamp,
            fps=self._metadata.fps
        )

        return frame, context
    
    def read_at(self, frame_number: int) -> tuple[np.ndarray, FrameContext] | None:
        """
        Seek to a frame number and read it in one call."""
        self.seek(frame_number)
        return self.read()
    
    def close(self) -> None:
        """Release the video capture."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "SeekableVideoSource":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
