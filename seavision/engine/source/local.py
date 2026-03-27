"""Loading a locally stored video file as a video source."""

from pathlib import Path
from typing import Iterator, Tuple
import cv2
import numpy as np
import subprocess

from .base import FrameContext, VideoMetadata, VideoSource


class LocalVideoSource(VideoSource):
    """
    Loads video frames from a local file using OpenCV.
    
    Attributes:
        file_path: Path to the local video file.

    Methods:
        get_metadata: Get metadata about the video file.
        iter_frames: Iterate over frames in the video file.
        process_gopro: Process GoPro video to strip audio stream.
        close: Release the video capture resource.
    
    Example:
        with LocalVideoSource("footage/clip_001.ts") as source:
            metadata = source.get_metadata()
            print(f"Processing {metadata.duration:.1f}s video")
            
            for frame, context in source.iter_frames():
                # process frame
                pass
    """

    def __init__(self, filepath: str):
        """
        Initialise the video source.

        Args:
            filepath: Path to the local video file.
        
        Raises:
            ValueError: If the video file cannot be opened
        """

        self.filepath = filepath
        self._cap = cv2.VideoCapture(filepath)
        
        if not self._cap.isOpened():
            raise ValueError(f"Cannot open video file: {filepath}")

    def get_metadata(self) -> VideoMetadata:
        """
        Get metadata about the video file.

        Returns:
            VideoMetadata object with file propoerties.
        """

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0.0

        return VideoMetadata(
            source_file=self.filepath,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            duration=duration
        )
    
    def iter_frames(self) -> Iterator[Tuple[np.ndarray, FrameContext]]:
        """
        Iterate over frames in the video file.

        Yields:
            Tuple of (frame, context) where frame is a BGR numpy array
            and context contains metadata about the frame.
        """

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        frame_number = 0

        while True:
            ret, frame = self._cap.read()

            if not ret:
                break
            
            timestamp = frame_number / fps if fps > 0 else 0.0
            context = FrameContext(
                source_file=self.filepath,
                frame_number=frame_number,
                timestamp=timestamp,
                fps=fps
            )

            yield frame, context
            frame_number += 1

    def process_gopro(self, processed_path: Path, overwrite: bool = False) -> None:
        """
        Method for processing local GoPro video to strip audio stream. This
        method uses ffmpeg to strip the audio stream from the video and save
        the processed video to the specified path.

        The LocalVideoSource object will point to the updated processed file
        after this method is called.

        An ffmpeg installation is required for this method to work.

        Args:
            processed_path: Path at which the processed output should be
                saved.
            overwrite: Whether to overwrite an existing processed file.
        
        Raises:
            FileExistsError: If the processed file already exists and
                overwrite is False.
        """

        # Ensure output path exists
        processed_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if the file already exists
        if processed_path.exists() and not overwrite:
            raise FileExistsError(f"Processed file already exists: {processed_path}")

        cmd = [
            "ffmpeg",
            "-i", str(self.filepath),
            "-y", # Overwrite output files without asking
            "-map", "0:v",  # Map only the video stream
            "-c", "copy",
            str(processed_path)
        ]

        subprocess.run(cmd, check=True)
        
        # Update path
        self.filepath = str(processed_path)

        # Update capture object
        self._cap.release()
        self._cap = cv2.VideoCapture(self.filepath)

    
    def close(self) -> None:
        """Release the video capture resource."""
        if self._cap is not None and self._cap.isOpened():
            self._cap.release()
            self._cap = None
