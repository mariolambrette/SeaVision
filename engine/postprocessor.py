"""Output formatting and CSV writing for detections."""

import csv
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .detectors import Detection

class OutputMode(Enum):
    """Output mode for detection results."""
    SINGLE_FILE = "single"  # All detections in one csv file
    PER_VIDEO = "per_video" # Separate CSV file for each video


@dataclass
class PostprocessorConfig:
    """
    Configuration for the detection postprocessor.

    Attributes:
        output_dir: DIrectory where the CSV files will be saved.
        output_mode: Whether to write all detections into a single CSV file or
            separate CSV files per video.
        single_file_name: Filename for single mode (default: 'detections.csv').
        overwrite: If True, overwrite existing files. If False, raise an error
            if the output file already exists.
    """

    output_dir: str = "./output"
    output_mode: OutputMode = OutputMode.PER_VIDEO
    single_file_name: str = "detections.csv"
    overwrite: bool = False
    

CSV_HEADERS = [
    "source_file",
    "timestamp",
    "frame_number",
    "xc",
    "yc",
    "width",
    "height",
    "confidence",
    "label,"
    "track_id",
]


class DetectionWriter:
    """
    Writes detection results to CSV files.

    Supports two output modes:
    - SINGLE_FILE: All detections written to one CSV file.
    - PER_VIDEO: Separate CSV file created for each source video.

    Example (single file mode):
        config = PostprocessorConfig(
            output_dir="./results",
            output_mode=OutputMode.SINGLE_FILE,
            overwrite=True
        )
        
        with DetectionWriter(config) as writer:
            for detection in detections:
                writer.write(detection)
    
    Example (per-video mode):
        config = PostprocessorConfig(
            output_dir="./results",
            output_mode=OutputMode.PER_VIDEO,
            overwrite=True
        )
        
        with DetectionWriter(config) as writer:
            for detection in all_detections:
                writer.write(detection)
            # Writer automatically creates new CSV when source_file changes
    """

    def __init__(self, config: Optional[PostprocessorConfig] = None):
        """
        Initialise the detection writer.
        
        Args:
            config: PostprocessorConfig object with output settings.
        """

        self.config = config or PostprocessorConfig()
        
        # Ensure output directory exists
        os.makedirs(self.config.output_dir, exist_ok=True)

        # State for file handling
        self._current_file: Optional[Path] = None
        self._current_writer: Optional[csv.DictWriter] = None
        self._current_source: Optional[str] = None
        self._detection_count: int = 0
    
    def write(self, detection: Detection) -> None:
        """
        Write a detection to the appropriate CSV file.

        Args:
            detection: Detection object to write.

        Raises:
            FileExistsError: If the output file already exists and overwrite
                is set to False.
        """

        # Handle file opening based on mode
        if self.config.output_mode == OutputMode.SINGLE_FILE:
            # Single file mode: open once on first write
            if self._current_file is None:
                self._open_single_file()
        
        else:
            # Per video mode: open a new file when source changed
            if detection.source_file != self._current_source:
                self._close_current_file()
                self._open_per_video_file(detection.source_file)

        # Write the detection
        self._current_writer.writerow(detection.to_csv_row())
        self._detection_count += 1
    
    def write_batch(self, detections: List[Detection]) -> None:
        """
        Write a batch of detections.

        Args:
            detections: List of Detection objects to write.
        """
        for detection in detections:
            self.write(detection)

    def finalise_video(self, source_file: str) -> None:
        """
        Finalise ouptut for a video, ensuring a CSV is created even if no
        detections were made.

        Call this after processing each video in PER_VIDEO mode to ensure all 
        videos with zero detections still get an empty CSV file.

        Args:
            source_file: Source video file path.
        """
        if self.config.output_mode == OutputMode.PER_VIDEO:
            # If we haven't written anything for this video, create empty file
            if self._current_source != source_file:
                self._close_current_file()
                self._open_per_video_file(source_file)
            # Close the file for this video
            self._close_current_file()
    
    def _open_file(self, filepath: Path) -> None:
        """
        Open a CSV file for writing, checking for overwrite permission.

        Args:
            filepath: Path to the CSV file to open.
        
        Raises:
            FileExistsError: If the file exists and overwrite is False.
        """

        # Check if file exists
        if filepath.exists():
            if not self.config.overwrite:
                raise FileExistsError(
                    f"Output file already exists: {filepath}. "
                    f"Set overwrite=True to overwrite."
                )
            else:
                print(f"WARNING: Overwriting existing file: {filepath}")
        
        # Open file
        self._current_file = open(filepath, mode="w", newline="", encoding="utf-8")
        self._current_writer = csv.DictWriter(
            self._current_file,
            fieldnames=CSV_HEADERS
        )
        self._current_writer.writeheader()
    
    def _open_single_file(self) -> None:
        """Open the single output CSV file."""
        filepath = Path(self.config.output_dir) / self.config.single_file_name
        self._open_file(filepath)

    def _open_per_video_file(self, source_file: str) -> None:
        """Open a per-video output CSV file."""
        # Generate output filename based on source video name
        video_name = Path(source_file).stem
        filename = f"{video_name}_detections.csv"
        filepath = Path(self.config.output_dir) / filename
        
        # Open file
        self._open_file(filepath)
        self._current_source = source_file
    
    def _close_current_file(self) -> None:
        """Close the current output CSV file, if open."""
        if self._current_file is not None:
            self._current_file.close()
            self._current_file = None
            self._current_writer = None
            self._current_source = None
    
    def close(self) -> None:
        """Close any open files."""
        self._close_current_file()

    @property
    def detection_count(self) -> int:
        """Get the total number of detections written."""
        return self._detection_count

    def __enter__(self):
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_value, exc_tb):
        """Exit context manager, closing any open files."""
        self.close()
        return False
