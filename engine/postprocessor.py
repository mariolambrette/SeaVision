"""Postprocessing utilities and CSV writing for detections.

This module contains two main components:

1. Postprocessing abstractions and built-in implementations that operate on
    :class:`Detection` objects, either per-frame or per-video:

    - FramePostprocessor: transforms detections for a single frame (e.g. label
      filters, per-frame NMS)
    - VideoPostprocessor: transforms detections for an entire video at once 
      (e.g. motion-based track pruning with full temporal context).

2. CSV writers for persisting detections to disk (DetectionWriter).

The goal is to allow the SeaVision pipeline to be configured with an ordered
list of postprocessing stages, mixing frame-level and video-level operations
as needed for a given deployment.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Callable, 
    Dict, 
    List, 
    Literal,
    Optional,
    Protocol,
    Set,
    TypedDict
)
import numpy as np

from .detectors import Detection
from .source import FrameContext, VideoMetadata

# ==============================================================================
# CSV Output Configuration
# ==============================================================================

class OutputMode(Enum):
    """Output mode for detection results."""

    SINGLE_FILE = "single"  # All detections in one csv file
    PER_VIDEO = "per_video"  # Separate CSV file for each video


@dataclass
class CSVWriterConfig:
    """Configuration for the detection CSV writer.

    Attributes
    ----------
    output_dir:
        Directory where the CSV files will be saved.
    output_mode:
        Whether to write all detections into a single CSV file or separate
        CSV files per video.
    single_file_name:
        Filename for single mode (default: ``"detections.csv"``).
    overwrite:
        If True, overwrite existing files. If False, raise an error if the
        output file already exists.
    """

    output_dir: str = "./output"
    output_mode: OutputMode = OutputMode.PER_VIDEO
    single_file_name: str = "detections.csv"
    overwrite: bool = False
    

# ==============================================================================
# Postprocessor interfaces
# ==============================================================================


class FramePostprocessor(Protocol):
    """
    Operates on detections for a single frame, potentially with per-video state.

    Typical examples:

    - Confidence or size filters
    - Label-based filters
    - Per-frame non-maximum suppression (NMS)

    Frame post processors are called once per frame during the pipeline.
    """

    def reset_for_video(self, metadata: VideoMetadata) -> None:
        """Reset internal state for a new video."""
    
    def process_frame(
        self,
        detections: List[Detection],
        context: FrameContext,
    ) -> List[Detection]:
        """
        Process detections for one frame and return the transformed list.

        The caller is responsible for using the returned list; implementations
        should not mutate the input list in place.
        """
    
    def finalize_video(self) -> None:
        """Finalise any per-video state at the end of a video."""


class VideoPostprocessor(Protocol):
    """Operate on detections for an entire video at once.

    Frames and per-frame contexts are optional. Implementations that only
    depend on detections and metadata can ignore them, which avoids the need
    for the caller to buffer full-resolution frames in memory.
    """

    def process_video(
        self,
        detections_per_frame: List[List[Detection]],
        metadata: VideoMetadata,
        frames: Optional[List[np.ndarray]] = None,
        contexts: Optional[List[FrameContext]] = None,
    ) -> List[List[Detection]]:
        """Process full-video detections and return new per-frame detections.

        The returned list must have the same length as ``detections_per_frame``
        and correspond to frames in the same order.
        """

# ==============================================================================
# FramePostProcessors
# ==============================================================================


@dataclass
class LabelFilterConfig:
    """
    Simple label-based filtering configuration.

    Attributes
    ----------
    keep_labels:
        If not None, only detections whose `label` is in this set are kept.
    drop_labels:
        If not None, detections whose `label` is in this set are removed.

    When both are set, a detection is kept only if:

        (label in keep_labels or keep_labels is None)
        and (label not in drop_labels or drop_labels is None).
    """

    keep_labels: Optional[Set[str]] = None
    drop_labels: Optional[Set[str]] = None


class LabelFilter(FramePostprocessor):
    """Filter detections based on their string labels."""

    def __init__(self, config: Optional[LabelFilterConfig] = None) -> None:
        self.config = config or LabelFilterConfig()

    def reset_for_video(self, metadata: VideoMetadata) -> None:
        # Stateless per video.
        return None

    def finalize_video(self) -> None:
        # Stateless per video.
        return None

    def process_frame(
        self,
        detections: List[Detection],
        context: FrameContext,
    ) -> List[Detection]:
        if not detections:
            return []

        keep = self.config.keep_labels
        drop = self.config.drop_labels

        # No filtering requested.
        if keep is None and drop is None:
            return detections

        filtered: List[Detection] = []

        for d in detections:
            label = d.label

            if keep is not None and label not in keep:
                continue
            if drop is not None and label in drop:
                continue

            filtered.append(d)

        return filtered


@dataclass
class PerFrameNmsConfig:
    """
    Configuration for per-frame non-maximum suppression (NMS).

    Attributes
    ----------
    iou_threshold:
        IoU threshold above which a smaller box is suppressed.
    class_agnostic:
        If True, NMS is applied across all labels jointly.
        If False, NMS is applied independently per label.
    """

    iou_threshold: float = 0.7
    class_agnostic: bool = True


class PerFrameNmsPostprocessor(FramePostprocessor):
    """
    Apply greedy NMS to detections on a per-frame basis.
    
    Detections are sorted by area (largest first) and overlapping boxes with
    IoI greater than `iou_threshold` are supressed. When `class_agnostic` is 
    False, suppression is applied independently per label.
    """

    def __init__(self, config: Optional[PerFrameNmsConfig] = None) -> None:
        self.config = config or PerFrameNmsConfig()    

    def reset_for_video(self, metadata: VideoMetadata) -> None:
        # Stateless.
        return None

    def finalize_video(self) -> None:
        # Stateless.
        return None

    def process_frame(
        self,
        detections: List[Detection],
        context: FrameContext,
    ) -> List[Detection]:
        if not detections:
            return []

        # Group detections by label if class_agnostic is False.
        if self.config.class_agnostic:
            groups: Dict[Optional[str], List[Detection]] = {None: detections}
        else:
            groups = {}
            for d in detections:
                groups.setdefault(d.label, []).append(d)

        kept_all: List[Detection] = []
        for group in groups.values():
            kept_all.extend(self._nms_group(group))

        return kept_all

    def _nms_group(self, dets: List[Detection]) -> List[Detection]:
        if not dets:
            return []

        positives: List[Detection] = []
        others: List[Detection] = []

        # Separate detections with positive area from degenerate ones.
        for d in dets:
            if d.area > 0.0:
                positives.append(d)
            else:
                others.append(d)

        # Larger boxes first.
        positives.sort(key=lambda d: d.area, reverse=True)

        kept: List[Detection] = []

        for det in positives:
            if any(self._iou(det, k) > self.config.iou_threshold for k in kept):
                continue
            kept.append(det)

        # Preserve degenerate-area detections unchanged.
        kept.extend(others)
        return kept

    @staticmethod
    def _iou(a: Detection, b: Detection) -> float:
        ax1, ay1, ax2, ay2 = a.bbox
        bx1, by1, bx2, by2 = b.bbox

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0.0, inter_x2 - inter_x1)
        inter_h = max(0.0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        if inter_area <= 0.0:
            return 0.0

        area_a = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
        area_b = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
        denom = area_a + area_b - inter_area

        return inter_area / denom if denom > 0.0 else 0.0


# ==============================================================================
# VideoPostProcessors
# ==============================================================================


@dataclass
class MotionTrackVideoConfig:
    """
    Configuration for full-video motion-based track filtering.

    Attributes
    ----------
    window_seconds:
        Time window over which motion is evaluated.
    threshold_fraction:
        Tracks whose displacement is less than this fraction of a
        characteristic box size are dropped entirely.
    """

    window_seconds: float = 3.0
    threshold_fraction: float = 0.4


class MotionTrackVideoPostprocessor(VideoPostprocessor):
    """
    Drop entire tracks that exhibit too little motion over a time window.
    
    - For each track with enough detections (based on the fps and 
      window_seconds), measure the displacement of the box centre between the
      first detection and a later detection at least window_seconds away.
    - Compute a characteristic length scale from the mean of the first and
      target box areas.
    - If displacement < threshold_fraction * length_scale, the track is
      considered stationary and removed entirely.
    """

    def __init__(self, config: Optional[MotionTrackVideoConfig] = None) -> None:
        self.config = config or MotionTrackVideoConfig()

    def process_video(
        self,
        detections_per_frame: List[List[Detection]],
        metadata: VideoMetadata,
        frames: Optional[List[np.ndarray]] = None,
        contexts: Optional[List[FrameContext]] = None,
    ) -> List[List[Detection]]:
        fps = float(metadata.fps) if metadata.fps else 0.0
        if fps <= 0.0:
            return detections_per_frame

        min_frames = int(self.config.window_seconds * fps)
        if min_frames <= 1:
            return detections_per_frame

        # Build per-track history across the entire video.
        tracks: Dict[int, List[Detection]] = {}
        for frame_dets in detections_per_frame:
            for d in frame_dets:
                if d.track_id is None:
                    continue
                tracks.setdefault(d.track_id, []).append(d)

        drop_tracks: Set[int] = set()

        for track_id, dets in tracks.items():
            if not dets:
                continue

            dets_sorted = sorted(dets, key=lambda d: d.frame_number)
            if len(dets_sorted) < min_frames:
                continue

            first = dets_sorted[0]
            target = dets_sorted[-1]

            # Prefer timestamp-based window when available.
            if first.timestamp is not None:
                for d in dets_sorted:
                    if d.timestamp is not None and d.timestamp - first.timestamp >= self.config.window_seconds:
                        target = d
                        break

            # Characteristic box size from first and target detections.
            area_first = max(first.area, 1.0)
            area_last = max(target.area, 1.0)
            area_mean = max((area_first + area_last) * 0.5, 1.0)

            length_scale = math.sqrt(area_mean)
            threshold = self.config.threshold_fraction * length_scale

            dx = target.xc - first.xc
            dy = target.yc - first.yc
            displacement = math.hypot(dx, dy)

            if displacement < threshold:
                drop_tracks.add(track_id)

        if not drop_tracks:
            return detections_per_frame

        # Filter out detections from tracks to drop.
        filtered_per_frame: List[List[Detection]] = []
        for frame_dets in detections_per_frame:
            filtered_per_frame.append(
                [d for d in frame_dets if d.track_id not in drop_tracks]
            )

        return filtered_per_frame


# ==============================================================================
# Stage registry and construction helper
# ==============================================================================

StageKind = Literal["frame", "video"]

@dataclass
class PostprocessStage:
    """
    A single postprocessing stage with a concrete implementation.

    Attributes
    ----------
    kind:
        "frame" or "video".
    impl:
        Instance of FramePostprocessor or VideoPostprocessor.
    """

    kind: StageKind
    impl: object  # FramePostprocessor | VideoPostprocessor


class PostprocessorFactory(TypedDict):
    """Registry entry describing how to build a postprocessor stage."""

    kind: StageKind
    build: Callable[[dict], object]  # returns FramePostprocessor or VideoPostprocessor


POSTPROCESSOR_REGISTRY: Dict[str, PostprocessorFactory] = {
    "motion_track_video": {
        "kind": "video",
        "build": lambda cfg: MotionTrackVideoPostprocessor(
            MotionTrackVideoConfig(
                window_seconds=cfg.get("window_seconds", 3.0),
                threshold_fraction=cfg.get("threshold_fraction", 0.4),
            )
        ),
    },
    "label_filter": {
        "kind": "frame",
        "build": lambda cfg: LabelFilter(
            LabelFilterConfig(
                keep_labels=set(cfg.get("keep_labels", [])) or None,
                drop_labels=set(cfg.get("drop_labels", [])) or None,
            )
        ),
    },
    "nms": {
        "kind": "frame",
        "build": lambda cfg: PerFrameNmsPostprocessor(
            PerFrameNmsConfig(
                iou_threshold=cfg.get("iou_threshold", 0.7),
                class_agnostic=cfg.get("class_agnostic", True),
            )
        ),
    },
}


def build_postprocess_stages(config_dict: Optional[dict]) -> List[PostprocessStage]:
    """
    Build an ordered list of postprocessing stages from a configuration dict.

    Expected config format (e.g. from YAML):

        postprocess:
          stages:
            - type: motion_track_video
              window_seconds: 3.0
              threshold_fraction: 0.4
            - type: label_filter
              keep_labels: ["fish", "seal"]
            - type: nms
              iou_threshold: 0.7
              class_agnostic: false

    Parameters
    ----------
    config_dict:
        Dictionary under the top-level 'postprocess' key, or None.

    Returns
    -------
    List[PostprocessStage]
        Stages in the order declared in the configuration.
    """
    if not config_dict:
        return []

    stages_cfg = config_dict.get("stages", [])
    stages: List[PostprocessStage] = []

    for stage_cfg in stages_cfg:
        stage_type = stage_cfg.get("type")
        if stage_type not in POSTPROCESSOR_REGISTRY:
            # Unknown stage type – skip or raise, depending on policy.
            continue

        entry = POSTPROCESSOR_REGISTRY[stage_type]
        kind: StageKind = entry["kind"]
        impl = entry["build"](stage_cfg)
        stages.append(PostprocessStage(kind=kind, impl=impl))

    return stages


# =============================================================================
# CSV Writer
# =============================================================================


CSV_HEADERS = [
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


class DetectionWriter:
    """
    Writes detection results to CSV files.

    Supports two output modes:

    - SINGLE_FILE: all detections written to one CSV file.
    - PER_VIDEO: separate CSV file created for each source video.

    Examples
    --------
    Single file mode:

        config = CSVWriterConfig(
            output_dir="./results",
            output_mode=OutputMode.SINGLE_FILE,
            overwrite=True,
        )

        with DetectionWriter(config) as writer:
            for detection in detections:
                writer.write(detection)

    Per-video mode:

        config = CSVWriterConfig(
            output_dir="./results",
            output_mode=OutputMode.PER_VIDEO,
            overwrite=True,
        )

        with DetectionWriter(config) as writer:
            for detection in all_detections:
                writer.write(detection)
            # Writer automatically creates new CSV when source_file changes.
    """

    def __init__(self, config: Optional[CSVWriterConfig] = None):
        """
        Initialise the detection writer.
        
        Args:
            config: CSVWriterConfig object with output settings.
        """

        self.config = config or CSVWriterConfig()
        
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
