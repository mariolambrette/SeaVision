"""
Frame capture for the edge runtime.

Provides a simple iterator over frames from a camera device or video
file. This is the edge equivalent of SeaVision's VideoSource, stripped
to the minimum needed for continuous inference.

Dependencies: opencv-python-headless only.
"""

import logging
from typing import Iterator, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CaptureError(Exception):
    """Raised when the video source cannot be opened."""
    pass


class FrameCapture:
    """
    Reads frames from a camera or video file via OpenCV.

    Attributes:
        source: The source string or device index passed at construction.
        fps: Frames per second of the source (0 if unknown/camera).
        width: Frame width in pixels.
        height: Frame height in pixels.
    """

    def __init__(self, source: str):
        """
        Open a video source.

        Args:
            source: Either a string path to a video file, an RTSP URL, or a
                string-encoded integer for a cmaera device index 
                (e.g. "0" for /dev/video0).
        
        Raises:
            CaptureError: If the source cannot be opened.
        """
        self.source = source

        # Try to interpret as camera index
        try:
            device_index = int(source)
            self._cap = cv2.VideoCapture(device_index)
        except ValueError:
            # If it is a filepath or URL.
            self._cap = cv2.VideoCapture(source)
        
        if not self._cap.isOpened():
            raise CaptureError(f"Could not open video source: {source}")
        
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 0.0
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        logger.info(
            "Opened source: %s (%dx%d @ %.1f fps)",
            source, self.width, self.height, self.fps,
        )

    def iter_frames(
        self,
        frame_skip: int = 1,
    ) -> Iterator[Tuple[np.ndarray, int]]:
        """
        Yield (frame, frame_number) tuples.

        Args:
            frame_skip: Process every Nth frame (1 = every frame)
        
        Yields:
            Tuple of (BGR numpy array, frame number).
        """
        frame_number = 0

        while True:
            ret, frame = self._cap.read()
            if not ret:
                logger.info("End of source reached at frame %d", frame_number)
                break

            if frame_number % frame_skip == 0:
                yield frame, frame_number

            frame_number += 1

    def release(self) -> None:
        """Release the underlying VideoCapture."""
        if self._cap is not None:
            self._cap.release()
            logger.info("Capture released: %s", self.source)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
