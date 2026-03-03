"""Detection loading from various sources for post-hoc visualisation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional
import csv
import logging

from ..detectors.base import Detection

logger = logging.getLogger(__name__)


class DetectionSource(ABC):
    """
    Abstract base class for loading detection.
    
    Provides a common interface for different detection sources (CSV files,
    iterators, databases, etc) to be used with the visualiser.
    """

    @abstractmethod
    def get_detections_for_frame(self, frame_number: int) -> List[Detection]:
        """
        Get all detections for a specific frame number.
        
        Args:
            frame_number: The frame index to retrieve detections for.
        
        Returns:
            List of Detection objects for that frame (empty list if none).
        """
        pass


    @abstractmethod
    def get_source_file(self) -> str:
        """
        Get the source video file path these detections belong to.
        
        Returns:
            String path or URI of the source video.
        """
        pass


    @abstractmethod
    def get_frame_numbers_with_detections(self) -> List[int]:
        """
        Get list of frame numbers that have detections.
        
        Returns:
            Sorted list of frame numbers containing at least one detection.
        """
        pass


    def get_total_detection_count(self) -> int:
        """
        Get the total number of detections across all frames.
        
        Returns:
            Total detection count.
        """
        return sum(
            len(self.get_detections_for_frame(f))
            for f in self.get_frame_numbers_with_detections()
        )
    

    def get_frame_count_with_detections(self) -> int:
        """
        Get the number of frames that have at least one detection.
        
        Returns:
            Number of frames with detections.
        """
        return len(self.get_frame_numbers_with_detections())   


@dataclass
class FrameDetections:
    """
    Container for detections grouped by frame number.

    A simple data structure that can be used directly or as a base for more
    complex detection sources.

    Attributes:
        source_file: Path or URI of the source file
        detections_by_frame: Dictionary mapping frame numbers to lists of
            Detection objects.
    
    Example:
        detections = FrameDetections(
            source_file="s3://my-bucket/video.ts",
            detections_by_frame={
                10: [Detection(...), Detection(...)],
                15: [Detection(...)]
            }
        )
        frame_10_dets = detections.get_detections_for_frame(10)
    """
    source_file: str
    detections_by_frame: Dict[int, List[Detection]] = field(default_factory=dict)


    def get_detections_for_frame(self, frame_number: int) -> List[Detection]:
        """Get detections for a specific frame."""
        return self.detections_by_frame.get(frame_number, [])
    
    
    def get_frame_numbers_with_detections(self) -> List[int]:
        """Get sorted list of frame numbers with detections."""
        return sorted(self.detections_by_frame.keys())

    
    def add_detection(self, detection: Detection) -> None:
        """
        Add a detection to the appropriate frame.
        
        Args:
            detection: Detection to add.
        """
        frame_num = detection.frame_number
        if frame_num not in self.detections_by_frame:
            self.detections_by_frame[frame_num] = []
        self.detections_by_frame[frame_num].append(detection)


    def get_total_detection_count(self) -> int:
        """Get total number of detections."""
        return sum(len(dets) for dets in self.detections_by_frame.values())
        

class CSVDetectionLoader(DetectionSource):
    """
    Load detections from a CSV file.
    
    Expects CSV format matching Detection.to_csv_row() output:
        source_file, timestamp, frame_number, xc, yc, width, height, confidence
    
    Handles:
        - CSV files with headers
        - Multiple source files in one CSV (filterable)
        - Missing or empty confidence values
        - Whitespace in values
    
    Attributes:
        csv_path: Path to the CSV file.
        source_file_filter: If set, only load detections for this source.
    
    Example:
        # Load all detections from CSV
        loader = CSVDetectionLoader("results/detections.csv")
        
        # Load only detections for a specific video
        loader = CSVDetectionLoader(
            "results/all_detections.csv",
            source_file="footage/video_001.ts"
        )
        
        # Use with visualiser
        for frame_num in loader.get_frame_numbers_with_detections():
            detections = loader.get_detections_for_frame(frame_num)
    """

    # Expected CSV columns
    REQUIRED_COLUMNS = {
        "source_file",
        "timestamp",
        "frame_number",
        "xc",
        "yc",
        "width",
        "height"
    }
    OPTIONAL_COLUMNS = {
        "confidence"
    }


    def __init__(
        self, 
        csv_path: str, 
        source_file: Optional[str] = None
    ):
        """
        Load detections from CSV.
        
        Args:
            csv_path: Path to CSV file with detections.
            source_file: If provided, only load detections matching this source.
                Useful when a single CSV contains detections from multiple videos.
                If None and CSV contains multiple sources, uses the first one found.
        
        Raises:
            FileNotFoundError: If CSV file does not exist.
            ValueError: If CSV is missing required columns.
        """

        self._csv_path = Path(csv_path)
        self._source_file_filter = source_file
        self._detections_by_frame: Dict[int, List[Detection]] = {}
        self._source_file: str = ""
        self._sources_in_file: List[str] = []
        
        self._load()


    def _load(self) -> None:
        """
        Load and index detections from a CSV.
        """
        if not self._csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._csv_path}")

        logger.debug(f"Loading detections from CSV: {self._csv_path}")

        with open(self._csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Validate columns
            if reader.fieldnames is None:
                raise ValueError(
                    f"CSV file is empty or has no header: {self._csv_path}"
                )
            
            columns = set(reader.fieldnames)
            missing = self.REQUIRED_COLUMNS - columns
            if missing:
                raise ValueError(
                    f"CSV file is missing required columns: {missing}. "
                    f"Found: {columns}"
                )
            
            has_confidence = "confidence" in columns
            sources_seen: set = set()

            for row_num, row in enumerate(reader, start = 2):  # Start at 2 (1-indexed + header)
                try:
                    detection = self._parse_row(row, has_confidence)
                except (ValueError, KeyError) as e:
                    logger.warning(
                        f"Skipping invalid row {row_num} in {self._csv_path}: {e}"
                    )
                    continue
                    
                # Track sources seen
                sources_seen.add(detection.source_file)

                # Apply source filter
                if self._source_file_filter is not None:
                    if not self._matches_source(detection.source_file):
                        continue
                
                # Set source file from first matching detection
                if not self._source_file:
                    self._source_file = detection.source_file

                # Index by frame number
                frame_num = detection.frame_number
                if frame_num not in self._detections_by_frame:
                    self._detections_by_frame[frame_num] = []
                self._detections_by_frame[frame_num].append(detection)

            self._sources_in_file = sorted(sources_seen)
        
        # Logger summary
        total_detections = sum(len(d) for d in self._detections_by_frame.values())
        frame_count = len(self._detections_by_frame)

        logger.info(
            f"Loaded {total_detections} detections across {frame_count} frames "
            f"from: {self._csv_path}"
        )

        if len(self._sources_in_file) > 1:
            logger.debug(
                f"CSV contains {len(self._sources_in_file)} source files: "
                f"{self._sources_in_file}"
            )


    def _parse_row(
        self,
        row: Dict[str, str],
        has_confidence: bool
    ) -> Detection:
        """
        Parse a CSV row into a Detection object.

        Args:
            row: Dictionary from csv.DictReader.
            has_confidence: Whether the CSV has a confidence column.
        
        Returns:
            Detection object.
        
        Raises:
            ValueError: If required fields are missing or invalid.       
        """
        # Parse confidence (may be empty string or missing)
        confidence = None
        if has_confidence:
            conf_str = row.get("confidence", "").strip()
            if conf_str:
                confidence = float(conf_str)
        
        return Detection(
            source_file=row["source_file"].strip(),
            timestamp=float(row["timestamp"].strip()),
            frame_number=int(row["frame_number"].strip()),
            xc=float(row["xc"].strip()),
            yc=float(row["yc"].strip()),
            width=float(row["width"].strip()),
            height=float(row["height"].strip()),
            confidence=confidence,
        )

    
    def _matches_source(self, source_file: str) -> bool:
        """
        Check if a source file matches the filter.
        
        Handles potential differences in path formatting (e.g., relative vs
        absolute, different separators).
        
        Args:
            source_file: Source file path from detection.
        
        Returns:
            True if it matches the filter (or no filter set).
        """
        if self._source_file_filter is None:
            return True
        
        # Exact match
        if source_file == self._source_file_filter:
            return True
        
        # Try normalised path comparison for local files
        try:
            source_path = Path(source_file)
            filter_path = Path(self._source_file_filter)
            
            # Compare resolved paths if both are local files
            if source_path.exists() and filter_path.exists():
                return source_path.resolve() == filter_path.resolve()
            
            # Compare just the filename as fallback
            return source_path.name == filter_path.name
        except (OSError, ValueError):
            # Path comparison failed, stick with exact match (already False)
            return False    


    def get_detections_for_frame(self, frame_number: int) -> List[Detection]:
        """Get all detections for a specific frame number."""
        return self._detections_by_frame.get(frame_number, [])


    def get_source_file(self) -> str:
        """Get the source video file path."""
        return self._source_file
    

    def get_frame_numbers_with_detections(self) -> List[int]:
        """Get sorted list of frame numbers with detections."""
        return sorted(self._detections_by_frame.keys())
    

    @property
    def csv_path(self) -> Path:
        """Get the path to the CSV file."""
        return self._csv_path
    

    @property
    def sources_in_file(self) -> List[str]:
        """Get list of all source files found in the CSV."""
        return self._sources_in_file


class IteratorDetectionSource(DetectionSource):
    """
    Wrap an iterator of detections for use with visualiser.
    
    Buffers all detections into a frame-indexed structure for random access.
    Useful for streaming visualisation directly from detector output.
    
    Note:
        This class buffers ALL detections in memory. For very long videos
        with many detections, consider using CSVDetectionLoader instead
        (write to CSV first, then load).
    
    Attributes:
        source_file: Path or URI of the source video.
    
    Example:
        # From detector output
        detections = list(detector.process_frame(frame, context))
        source = IteratorDetectionSource(iter(detections), "video.ts")
        
        # From a generator
        def detection_generator():
            for frame_num in range(100):
                yield Detection(...)
        
        source = IteratorDetectionSource(detection_generator(), "video.ts")
    """
    def __init__(
        self,
        detections: Iterator[Detection],
        source_file: str,
    ):
        """
        Create detection source from iterator.
        
        Args:
            detections: Iterator yielding Detection objects.
            source_file: Source video file path/URI (for metadata).
        
        Note:
            The iterator is fully consumed during initialisation.
        """
        self._source_file = source_file
        self._detections_by_frame: Dict[int, List[Detection]] = {}
        self._buffer(detections)
    

    def _buffer(self, detections: Iterator[Detection]) -> None:
        """Buffer all detections into frame index."""
        count = 0
        for det in detections:
            frame_num = det.frame_number
            if frame_num not in self._detections_by_frame:
                self._detections_by_frame[frame_num] = []
            self._detections_by_frame[frame_num].append(det)
            count += 1
        
        logger.debug(
            f"Buffered {count} detections across "
            f"{len(self._detections_by_frame)} frames"
        )
    

    def get_detections_for_frame(self, frame_number: int) -> List[Detection]:
        """Get all detections for a specific frame number."""
        return self._detections_by_frame.get(frame_number, [])
    

    def get_source_file(self) -> str:
        """Get the source video file path."""
        return self._source_file
    

    def get_frame_numbers_with_detections(self) -> List[int]:
        """Get sorted list of frame numbers with detections."""
        return sorted(self._detections_by_frame.keys())


class ListDetectionSource(DetectionSource):
    """
    Create detection source from a list of detections.
    
    Simpler alternative to IteratorDetectionSource when detections
    are already in a list.
    
    Example:
        detections = [det1, det2, det3]
        source = ListDetectionSource(detections, "video.ts")
    """
    
    def __init__(
        self,
        detections: List[Detection],
        source_file: str,
    ):
        """
        Create detection source from list.
        
        Args:
            detections: List of Detection objects.
            source_file: Source video file path/URI (for metadata).
        """
        self._source_file = source_file
        self._detections_by_frame: Dict[int, List[Detection]] = {}
        
        for det in detections:
            frame_num = det.frame_number
            if frame_num not in self._detections_by_frame:
                self._detections_by_frame[frame_num] = []
            self._detections_by_frame[frame_num].append(det)

    
    def get_detections_for_frame(self, frame_number: int) -> List[Detection]:
        """Get all detections for a specific frame number."""
        return self._detections_by_frame.get(frame_number, [])
    

    def get_source_file(self) -> str:
        """Get the source video file path."""
        return self._source_file
    

    def get_frame_numbers_with_detections(self) -> List[int]:
        """Get sorted list of frame numbers with detections."""
        return sorted(self._detections_by_frame.keys())


def load_detections_from_csv(
    csv_path: str,
    source_file: Optional[str] = None,
) -> FrameDetections:
    """
    Convenience function to load detections from CSV into a FrameDetections object.
    
    Args:
        csv_path: Path to CSV file.
        source_file: Optional source file filter.
    
    Returns:
        FrameDetections container with loaded detections.
    
    Example:
        detections = load_detections_from_csv("results.csv")
        for frame_num in detections.get_frame_numbers_with_detections():
            frame_dets = detections.get_detections_for_frame(frame_num)
    """
    loader = CSVDetectionLoader(csv_path, source_file)
    
    frame_detections = FrameDetections(
        source_file=loader.get_source_file(),
        detections_by_frame={
            frame_num: loader.get_detections_for_frame(frame_num)
            for frame_num in loader.get_frame_numbers_with_detections()
        }
    )
    
    return frame_detections
