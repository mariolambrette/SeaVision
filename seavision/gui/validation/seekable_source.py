"""Random access video source for the GUI viewer."""

import cv2
import numpy as np
from pathlib import Path
import logging

from seavision.engine.source.base import FrameContext, VideoMetadata

logger = logging.getLogger(__name__)

# Container formats where cv2.VideoCapture seeking is unreliable.
# These use byte-offset estimation rather than a frame index table,
# causing decoder state corruption on seek-back.
_PRELOAD_EXTENSIONS = frozenset({
    ".ts", ".mts", ".m2ts",   # MPEG transport streams
})


def _needs_preload(filepath: str) -> bool:
    """Check whether a file's container format requires pre-loading."""
    return Path(filepath).suffix.lower() in _PRELOAD_EXTENSIONS


def _estimate_memory_mb(width: int, height: int, frame_count: int) -> float:
    """Estimate memory usage for pre-loading all frames, in MB."""
    bytes_per_frame = width * height * 3  # BGR uint8
    return (bytes_per_frame * frame_count) / (1024 * 1024)


def _available_memory_mb() -> float | None:
    """
    Return available system RAM in MB, or None if it can't be determined.

    Uses psutil if available. This is an optional dependency — the GUI
    works without it, the dialog just won't show available RAM.
    """
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 * 1024)
    except ImportError:
        return None


class SeekableVideoSource:
    """
    Random-access wrapper around cv2.VideoCapture.

    Unlike LocalVideoSource (which iterates sequentially), this class supports
    seeking to arbitrary frame numbers. Designed for the GUI viewer where the
    user may jump around in the video timeline.

    Compatible only with local video files, not live network streams.

    Supports two modes:
        1. preload=True: all frames decoded sequentially into memory on
           construction. Every access is an 0(1) array lookup. Frame-accurate
           for all container formats. Uses (width * height * 3 * frames)
           bytes of RAM.
        2. preload=False: uses cv2.VideoCapture seeking directly. Fast and
           memory-efficient, but seeking accuracy depends on the container
           format.

    Usage:
        with SeekableVideoSource("video.ts") as src:
            frame, ctx = src.read_at(47)
            frame, ctx = src.read_at(183)
    """

    def __init__(self, filepath: str, preload: bool = False) -> None:
        self._filepath = filepath
        self._preload = preload

        if not Path(self._filepath).exists():
            raise ValueError(f"Video file not found: {self._filepath}")
        
        self._metadata = self._read_metadata(filepath)
        self._frame_counter = 0
        self._frames: list[np.ndarray] = []
        self._cap: cv2.VideoCapture | None = None

        if preload:
            self._frames = self._preload_frames(filepath)
             # Correct frame count to match actual decoded frames
            if len(self._frames) != self._metadata.frame_count:
                self._metadata = VideoMetadata(
                    source_file=self._metadata.source_file,
                    fps=self._metadata.fps,
                    frame_count=len(self._frames),
                    width=self._metadata.width,
                    height=self._metadata.height,
                    duration=len(self._frames) / self._metadata.fps
                    if self._metadata.fps > 0 else 0.0,
                )
        else:
            self._cap = cv2.VideoCapture(self._filepath)
            if not self._cap.isOpened():
                raise ValueError(f"Failed to open video: {self._filepath}")


    @staticmethod
    def _read_metadata(filepath:str) -> VideoMetadata:
        """Read video metadata without disturbing the main decode."""
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            raise ValueError(f"Failed to open video file: {filepath}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0.0

            return VideoMetadata(
                source_file=filepath,
                fps=fps,
                frame_count=frame_count,
                width=width,
                height=height,
                duration=duration,
            )
        finally:
            cap.release()

    @staticmethod
    def _preload_frames(filepath: str) -> list[np.ndarray]:
        """
        Sequentially read every frame into memory.

        Uses a fresh capture with no prior seeking — the exact same
        decode path as LocalVideoSource.iter_frames(). This guarantees
        frame numbering matches the pipeline that generated detections.
        """
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            raise ValueError(f"Failed to open video file: {filepath}")

        frames: list[np.ndarray] = []
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)
        finally:
            cap.release()

        size_mb = sum(f.nbytes for f in frames) / (1024 * 1024)
        logger.info(
            "Pre-loaded %d frames from %s (%.1f MB)",
            len(frames),
            Path(filepath).name,
            size_mb,
        )

        if not frames:
            raise ValueError(f"No frames could be read from: {filepath}")

        return frames
    
    @property
    def metadata(self) -> VideoMetadata:
        """Cached video metadata."""
        return self._metadata
    
    def _make_context(self, frame_number: int) -> FrameContext:
        """Build a FrameContext for the given frame number."""
        fps = self._metadata.fps
        return FrameContext(
            frame_number=frame_number,
            timestamp=frame_number / fps if fps > 0 else 0.0,
            source_file=self._filepath,
            fps=fps,
        )
    
    def _clamp(self, frame_number: int) -> int:
        """Clamp a frame number to the valid range."""
        if self._preload:
            max_frame = len(self._frames) - 1
        else:
            max_frame = self._metadata.frame_count - 1
        return max(0, min(frame_number, max_frame))

    def seek(self, frame_number: int) -> None:
        """
        Seek to a specific frame number.

        The frame number is clamped to the valid range. This prevents invalid
        frames being read causing hidden failures.
        
        In preload mode, the internal counter is updated. Otherwise, the
        underlying capture is seeked using CAP_PROP_POS_FRAMES.
        """
        clamped = self._clamp(frame_number)
        
        if self._preload:
            self._frame_counter = clamped
        else:
            if self._cap is None:
                return
            
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, clamped)
            self._frame_counter = clamped

    def read(self) -> tuple[np.ndarray, FrameContext] | None:
        """
        Read the current frame and advance the position.

        returns:
            Tuple of (frame, context) or None if at the end of the video or the
            frame could not be decoded.
        """
        if self._preload:
            if self._frame_counter >= len(self._frames):
                return None
            frame = self._frames[self._frame_counter].copy()
        else:
            if self._cap is None:
                return None
            ret, frame = self._cap.read()
            if not ret:
                return None

        ctx = self._make_context(self._frame_counter)
        self._frame_counter += 1
        return frame, ctx
    
    def read_at(self, frame_number: int) -> tuple[np.ndarray, FrameContext] | None:
        """
        Seek to a frame and read it in one call.
        """
        if self._preload:
            if not self._frames:
                return None
            clamped = self._clamp(frame_number)
            frame = self._frames[clamped].copy()
        else:
            if self._cap is None:
                return None
            clamped = self._clamp(frame_number)
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, clamped)
            ret, frame = self._cap.read()
            if not ret:
                return None

        ctx = self._make_context(clamped)
        self._frame_counter = clamped + 1
        return frame, ctx

    def close(self) -> None:
        """Release the video capture."""
        self._frames = []
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "SeekableVideoSource":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
