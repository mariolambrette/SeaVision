"""
Detection CSV writer for the edge runtime.

Produces CSV files with the same column schema as SeaVIsion's DetectionWriter, 
so edge detections can be loaded directly into the validation GUI. The writer
 buffers rows in memory and flushes periodically to balance write performance
 against data safety and memory usage.

 Dependencies: Only python standard libraries.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# CSV column order — must match seavision.engine.postprocessor.CSV_HEADERS
CSV_COLUMNS = [
    "source_file",
    "timestamp",
    "frame_number",
    "xc",
    "yc",
    "width",
    "height",
    "confidence",
    "label",
    "track_id",
]


class EdgeDetectionWriter:
    """
    Writes detections to CSV files in SeaVision-compatible format.

    Creates one CSV per recording session (or per video file if processing 
    files rather than live camera). Buffers rows in memory and flushes every
    `flush_interval` frames.

    Attributes:
        output_dir: Directory where CSV files will be saved.
        flush_interval: Number of frames between flushes to disk.
    """

    def __init__(
        self,
        output_dir: str,
        source_name: str = "camera",
        flush_interval: int = 100,
    ):
        """
        Initialise the writer.

        Args:
            output_dir: Directory for output files. Created if needed.
            source_name: Name of the source, used in filenames and in
                the source_file column.
            flush_interval: Flush to disk every N frames.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.source_name = source_name
        self.flush_interval = flush_interval

        # Generate a timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_path = self.output_dir / f"detections_{timestamp}.csv"

        self._buffer: List[Dict] = []
        self._file = None
        self._writer = None
        self._frames_since_flush = 0
        self._total_detections = 0

        # Open and write header
        self._file = open(self._csv_path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=CSV_COLUMNS)
        self._writer.writeheader()
        self._file.flush()

        logger.info("Detection writer opened: %s", self._csv_path)

    def write(
        self,
        detections: List[Tuple[float, float, float, float, float, int]],
        frame_number: int,
        timestamp: float = 0.0,
        class_names: Optional[Dict[int, str]] = None,
    ) -> None:
        """
        Write detections for a single frame.

        Args:
            detections: List of (x1, y1, x2, y2, confidence, class_id)
                tuples in pixel coordinates.
            frame_number: Frame index.
            timestamp: Timestamp in seconds from start of source.
            class_names: Optional mapping of class_id to label string.
        """
        for x1, y1, x2, y2, conf, cls_id in detections:
            # Convert xyxy to xc,yc,w,h to match SeaVision's Detection format
            w = x2 - x1
            h = y2 - y1
            xc = x1 + w / 2.0
            yc = y1 + h / 2.0

            label = ""
            if class_names and cls_id in class_names:
                label = class_names[cls_id]

            self._buffer.append({
                "source_file": self.source_name,
                "timestamp": f"{timestamp:.3f}",
                "frame_number": frame_number,
                "xc": f"{xc:.1f}",
                "yc": f"{yc:.1f}",
                "width": f"{w:.1f}",
                "height": f"{h:.1f}",
                "confidence": f"{conf:.4f}",
                "label": label,
                "track_id": "",
            })

        self._total_detections += len(detections)
        self._frames_since_flush += 1

        if self._frames_since_flush >= self.flush_interval:
            self.flush()

    def flush(self) -> None:
        """Write buffered rows to disk."""
        if not self._buffer:
            return
        
        if self._writer is not None and self._file is not None:
            self._writer.writerows(self._buffer)
            self._file.flush()
            self._buffer.clear()
            self._frames_since_flush = 0

    def close(self) -> None:
        """Flush remaining buffer and close the file."""
        self.flush()
        if self._file is not None:
            self._file.close()
            self._file = None

        logger.info(
            "Detection writer closed: %s (%d detections)",
            self._csv_path, self._total_detections,
        )

    @property
    def csv_path(self) -> Path:
        """Path to the current CSV file."""
        return self._csv_path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
