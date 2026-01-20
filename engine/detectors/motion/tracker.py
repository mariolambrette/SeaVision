"""Simple multi-object tracker for persistence filtering."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class TrackedObject:
    """A tracked detection across multiple frames."""

    track_id: int
    xc: float
    yc: float
    width: float
    height: float
    age: int = 1 # Frames since first seen
    frames_since_update: int = 0 # Frames since last matched


    def update(self, xc: float, yc: float, width: float, height: float) -> None:
        """Update the tracked object with new detection data."""
        self.xc = xc
        self.yc = yc
        self.width = width
        self.height = height
        self.age += 1
        self.frames_since_update = 0

    def mark_missed(self) -> None:
        """Mark that no detection matched this frame."""
        self.frames_since_update += 1

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Get bounding box as (x1, y1, x2, y2)."""
        x1 = self.xc - self.width / 2
        y1 = self.yc - self.height / 2
        x2 = self.xc + self.width / 2
        y2 = self.yc + self.height / 2
        return (x1, y1, x2, y2)


@dataclass
class TrackerConfig:
    """Configuration for the persistence tracker."""

    min_persistence: int = 3      # Frames before emitting detection
    max_frames_missing: int = 5   # Frames before dropping track
    iou_threshold: float = 0.3    # Minimum IoU to match detections


def compute_iou(box1: Tuple[float, float, float, float], 
                box2: Tuple[float, float, float, float]) -> float:
    """Compute Intersection over Union between two boxes (x1,y1,x2,y2)."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0


class PersistenceTracker:
    """
    tracks detections across frames and filters out transient noise.

    Only emits detections that have persisted for min_persistence frames.

    Example:
        tracker = PersistenceTracker(TrackerConfig(min_persistence=3))
        
        for frame_detections in all_detections:
            confirmed = tracker.update(frame_detections)
            # confirmed only contains detections seen for 3+ frames
    """

    def __init__(self, config: Optional[TrackerConfig] = None):
        self.config = config or TrackerConfig()
        self._tracks: Dict[int, TrackedObject] = {}
        self._next_id: int = 0

    def update(self, detections: List[dict]) -> List[TrackedObject]:
        """
        Update tracker with new frame detections.

        Args:
            detections: List of detection dicts with keys:
                'xc', 'yc', 'width', 'height'.
        
        Returns:
            A list of tracked objects that have a persistence >= 
            min_persistence frames.
        """

        # Convert detections to bbox format for matching
        det_boxes = []
        for det in detections:
            x1 = det["xc"] - det["width"] / 2
            y1 = det["yc"] - det["height"] / 2
            x2 = det["xc"] + det["width"] / 2
            y2 = det["yc"] + det["height"] / 2
            det_boxes.append((x1, y1, x2, y2))

        # Match detections to existing tracks using IoU
        matched_tracks = set()
        matched_dets = set()

        # Greedy matching, highest IoU first
        if self._tracks and det_boxes:
            iou_matrix = []

            for track_id, track in self._tracks.items():
                for det_idx, det_box in enumerate(det_boxes):
                    iou = compute_iou(track.bbox, det_box)
                    if iou >= self.config.iou_threshold:
                        iou_matrix.append((iou, track_id, det_idx))
            
            # Sort by IoU descending
            iou_matrix.sort(reverse=True, key=lambda x: x[0])

            for iou, track_id, det_idx in iou_matrix:
                if track_id not in matched_tracks and det_idx not in matched_dets:
                    # Update track with matched detection
                    det = detections[det_idx]
                    self._tracks[track_id].update(
                        det["xc"], det["yc"], det["width"], det["height"]
                    )
                    matched_tracks.add(track_id)
                    matched_dets.add(det_idx)
        
        # Mark unmatched tracks as missed
        for track_id in self._tracks:
            if track_id not in matched_tracks:
                self._tracks[track_id].mark_missed()
        
        # Create new tracks for unmatched detections
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_dets:
                self._tracks[self._next_id] = TrackedObject(
                    track_id=self._next_id,
                    xc=det["xc"],
                    yc=det["yc"],
                    width=det["width"],
                    height=det["height"],
                )
                self._next_id += 1

        # Remove stale tracks
        stale_ids = [
            track_id for track_id, track in self._tracks.items()
            if track.frames_since_update > self.config.max_frames_missing
        ]
        for track_id in stale_ids:
            del self._tracks[track_id]

        # Return only tracks that have persisted long enough
        confirmed = [
            track for track in self._tracks.values()
            if track.age >= self.config.min_persistence
        ]

        return confirmed
    
    def reset(self) -> None:
        """Reset the tracker state for a new video."""
        self._tracks.clear()
        self._next_id = 0
