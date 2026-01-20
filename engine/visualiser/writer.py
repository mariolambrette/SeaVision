"""Video file writing management."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Optional
import re
import cv2
import numpy as np

from engine.source.base import VideoMetadata
from engine.visualiser.config import VideoOutputConfig


# Type alias for custom naming functions
# Takes VideoMatadata, returns the output filename stem 
# (without suffix/extension)
OutputNameFunction = Callable[[VideoMetadata], str]

def extract_output_stem(
    source_file: str,
    include_parents: int = 2
) -> str:
    """
    Extract a suitable output filename stem from a source file path or URI.

    Handles both local paths and S3 URIs, including enough path components to
    avoid collisions when multiple videos have the same filename.

    Args:
        source_file: Source file path or S3 URI.
        include_parents: Number of parent directories to include in the output
            stem to help avoid name collisions. Default is 2.

    Returns:
        A sanitised string suitable for use as a filename stem.

    Examples:
        # Local path
        extract_output_stem("/home/user/footage/2025-01-15/video_001.ts")
        # -> "2025-01-15_video_001"
        
        # S3 URI
        extract_output_stem("s3://bucket/device1/cam1/2025-01-15/video_001.ts")
        # -> "cam1_2025-01-15_video_001"
        
        # S3 URI with more context
        extract_output_stem("s3://bucket/device1/cam1/2025-01-15/video_001.ts", include_parents=3)
        # -> "device1_cam1_2025-01-15_video_001"
    """

    # Handle S3 URIs - extract the key portion
    s3_match = re.match(r"^s3://[^/]+/(.+)$", source_file)
    if s3_match:
        # Use PurePosixPath for S3 keys (always forward slashes)
        path = PurePosixPath(s3_match.group(1))
    else:
        # Local path
        path = Path(source_file)    

    # Get the filename stem
    stem = path.stem

    # Build output stem with parent directories
    parts = []
    for i in range(min(include_parents, len(list(path.parents)) - 1)):
        parent_name = path.parents[i].name
        if parent_name:  # Skip empty names (root)
            parts.insert(0, parent_name)
    parts.append(stem)

    # Join with underscores and sanitise
    output_stem = "_".join(parts)
    
    # Remove any characters that might cause filesystem issues
    output_stem = re.sub(r'[<>:"/\\|?*]', '_', output_stem)
    
    return output_stem


def sanitise_filename(name: str) -> str:
    """
    Sanitise a string to be safe for use as a filename.

    Replaces or removes characters that are invalid in filenames across
    common operating systems.

    Args:
        name: Input string to sanitize.

    Returns:
        Sanitized filename string.
    """
    # Replace problematic characters with underscores
    sanitised = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    
    # Collapse multiple underscores
    sanitised = re.sub(r'_+', '_', sanitised)
    
    # Strip leading/trailing underscores and whitespace
    sanitised = sanitised.strip('_ ')
    
    # Ensure we have something left
    if not sanitised:
        sanitised = "output"
    
    return sanitised


@dataclass
class VideoWriterHandle:
    """
    Manages the lifecycle of a video file writer.

    Handles opening, writing frames, and closing video files.
    Uses context manager pattern for safe resource cleanup.

    Output naming priority:
        1. Custom naming function (if provided)
        2. Default naming using extact_output_stem()

    Example with custom naming:
        def my_namer(meta: VideoMetadata) -> str:
            # Extract device and date from S3 path
            parts = meta.source_file.split('/')
            return f"{parts[-3]}_{parts[-2]}_{Path(meta.source_file).stem}"
        
        with VideoWriterHandle(config, metadata, name_function=my_namer) as writer:
            ...
    """

    config: VideoOutputConfig
    metadata: VideoMetadata
    name_function: Optional[OutputNameFunction] = None
    _writer: Optional[cv2.VideoWriter] = field(default=None, init=False)
    _output_path: Optional[Path] = field(default=None, init=False)
    _frame_count: int = field(default=0, init=False)

    def __post_init__(self):
        """Initialise and open the video writer."""
        self._output_path = self._build_output_path()
        self._ensure_output_dir()
        self._check_overwrite()
        self._open_writer()

    def _build_output_path(self) -> Path:
        """
        Build the output file path from config and metadata.
        
        Uses custom name function if provided, otherwise falls back to
        extract_output_stem() with configured parent directory depth.
        """
        output_dir = Path(self.config.output_dir)
        
        # Determine the output stem
        if self.name_function is not None:
            # Use custom naming function
            stem = self.name_function(self.metadata)
            stem = sanitise_filename(stem)
        else:
            # Default naming with parent directory context
            stem = extract_output_stem(
                self.metadata.source_file,
                include_parents=self.config.include_parent_dirs
            )
        
        output_name = stem + self.config.filename_suffix + self.config.format
        return output_dir / output_name
    

    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self._output_path.parent.mkdir(parents=True, exist_ok=True)


    def _check_overwrite(self) -> None:
        """Check if output file exists and handle based on config."""
        if self._output_path.exists() and not self.config.overwrite:
            raise FileExistsError(
                f"Output file already exists: {self._output_path}. "
                "Set overwrite=True to replace."
            )


    def _open_writer(self) -> None:
        """Open the cv2 VideoWriter with the specified configuration."""

        fourcc = cv2.VideoWriter_fourcc(*self.config.codec)
        fps = self.config.fps or self.metadata.fps

        self._writer = cv2.VideoWriter(
            str(self._output_path),
            fourcc,
            fps,
            (self.metadata.width, self.metadata.height)
        )

        if not self._writer.isOpened():
            raise RuntimeError(
                f"Failed to open video writer for {self._output_path}"
            )
    

    def write(self, frame: np.ndarray) -> None:
        """
        Write a frame to the video file.

        Args:
            frame: BGR image as a numpy array.

        Raises:
            RuntimeError: If the writer is not opened.
        """

        if self._writer is None:
            raise RuntimeError("Video writer is not opened.")
        
        self._writer.write(frame)
        self._frame_count += 1
    

    def close(self) -> None:
        """Release the video writer resource."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None


    @property
    def frame_count(self) -> int:
        """Get the number of frames written."""
        return self._frame_count

    
    @property
    def output_path(self) -> Optional[Path]:
        """Get the output file path."""
        return self._output_path
    

    def __enter__(self) -> "VideoWriterHandle":
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False
