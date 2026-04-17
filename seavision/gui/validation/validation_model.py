"""
Validation model for the SeaVision review workflow.

Wraps raw Detection objects with mutable review status, providing the core data
layer for confirm/reject/skip operations and manual data addition in the review
UI.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QObject, Signal

from seavision.engine.detectors.base import Detection
from seavision.engine.visualiser import CSVDetectionLoader

class ValidationStatus(Enum):
    """Review status for a detection."""
    PENDING = auto()
    CONFIRMED = auto()
    REJECTED = auto()
    SKIPPED = auto()
    CORRECTED = auto()


@dataclass
class ValidatedDetection:
    """
    A detection with mutable review status.

    Wraps an immutable engine Detection with the fields the GUI needs to
    track: a unique ID, a review status, an origin flag, and optional
    geometry corrections.

    Attributes:
        detection: The original Detection from the pipeline, or a synthetic
            Detection for manually added detections.
        status: Current review status (starts as PENDING for pipeline
            detections, CORRECTED for manual additions).
        id: Unique integer ID, assigned sequentially when the model is
            constructed or when a detection is added. Stable for the
            lifetime of the session.
        is_manual: True if this detection was added by the reviewer reather
            than loaded from the pipeline CSV. Affects export behaviour,
            visual styling and performance evalutation.
        corrected_geometry: If the reviewer adjusts the bounding box the
            new geometry is stored here as:
            {"xc": float, "yc": float, "width": float, "height": float}.
            None means the original geometry is unchanged.
    """

    detection: Detection
    status: ValidationStatus = ValidationStatus.PENDING
    id: int = 0
    is_manual: bool = False
    corrected_geometry: Optional[dict] = field(default=None, repr=False)
    

class ValidationModel(QObject):
    """
    Central data model for the review workflow.

    Wraps a detection source (typically a CSVDetectionLoader) with mutable
    review status. Provides methods to query and update detection statuses, add
    new detections, and emits signals when state changes so that UI components
    can react.

    The model is constructed once per session and lives for the session's
    duration. It does not own the video source or any display widgets - it is
    purely data and logic.
    """

    # Emitted when a single detection's status changes.
    # Args: (detection_id: int, new_status: ValidationStatus)
    detection_status_changed = Signal(int, object)

    # Emitted after any status change with updated progress counts.
    # Args: (progress_dict: dict) - keys are status names, values are counts.
    progress_changed = Signal(object)

    # Emitted when a new detection is added manually.
    # Args: (validated_detection: ValidatedDetection)
    detection_added = Signal(object)

    # Emitted when a detection is removed (undo of a manual add).
    # Args: (detection_id: int)
    detection_removed = Signal(int)

    def __init__(self, detection_source: CSVDetectionLoader, parent=None):
        """
        Build the validation model from a detection source.

        Args:
            detection_source: A CSVDetectionLoader (or any object with
                get_detections_for_frame() and sources_in_file).
            parent: Optional QObject parent for memory management.
        """
        super().__init__(parent)

        self._source = detection_source
        self._detections: list[ValidatedDetection] = []
        self._by_id: dict[int, ValidatedDetection] = {}
        self._by_video: dict[str, list[ValidatedDetection]] = {}
        self._by_frame: dict[tuple[str, int], list[ValidatedDetection]] = {}
        self._labels: set[str] = set()
        self._next_id: int = 0

        self._build_from_source()

    # --- Create the validation model from a source ---
    def _build_from_source(self) -> None:
        """
        Flatten all detections from the source into ValidatedDetection
        objects with sequential IDs and build lookup indexes.
        """
        for frame_num in self._source.get_frame_numbers_with_detections():
            for det in self._source.get_detections_for_frame(frame_num):
                vd = ValidatedDetection(
                    detection=det,
                    status=ValidationStatus.PENDING,
                    id=self._next_id,
                    is_manual=False,
                )
                self._index_detection(vd)
                self._next_id += 1

                if det.label:
                    self._labels.add(det.label)

    def _index_detection(self, vd: ValidatedDetection) -> None:
        """Add a ValidatedDetection to all internal indexes."""
        self._detections.append(vd)
        self._by_id[vd.id] = vd

        source_file = vd.detection.source_file
        self._by_video.setdefault(source_file, []).append(vd)

        key = (source_file, vd.detection.frame_number)
        self._by_frame.setdefault(key, []).append(vd)

    # --- Reading methods ---
    def get_detections_for_video(
        self, source_file: str
    ) -> list[ValidatedDetection]:
        """Return all detections for a given source video."""
        return self._by_video.get(source_file, [])
    
    def get_detections_for_frame(
            self, source_file: str, frame_number: int
    ) -> list[ValidatedDetection]:
        """Return all detections for a specific frame of a specified video."""
        return self._by_frame.get((source_file, frame_number), [])
    
    def get_all_source_files(self) -> list[str]:
        """Return all unique source file paths, in insertion order."""
        return list(self._by_video.keys())
    
    def get_progress(self, source_file: str) -> dict:
        """
        Return review progress counts for a specific video.

        Returns:
            Dict with keys: "confirmed", "rejected", "skipped", "corrected",
            "pending", "manual", "total", "reviewed"
        """

        detections = self.get_detections_for_video(source_file)
        counts = {
            "confirmed": 0,
            "rejected": 0,
            "skipped": 0,
            "corrected": 0,
            "pending": 0,
            "manual": 0,
        }
        for vd in detections:
            counts[vd.status.name.lower()] += 1
            if vd.is_manual:
                counts["manual"] += 1

        counts["total"] = len(detections)
        counts["reviewed"] = counts["total"] - counts["pending"]
        return counts
    
    # --- Set detection status ---
    def set_status(
        self, detection_id: int, new_status: ValidationStatus
    ) -> None:
        """
        Update the review status of a detection.

        Emits detection_status_changed and progress_changed signals.

        Args:
            detection_id: The unique ID of the detection to update.
            new_status: The new ValidationStatus to assign.

        Raises:
            KeyError: If detection_id is not found.
        """
        if detection_id not in self._by_id:
            raise KeyError("detection_id not found")
        
        vd = self._by_id.get(detection_id)
        vd.status = new_status

        self.detection_status_changed.emit(detection_id, new_status)

        source_file = vd.detection.source_file
        progress = self.get_progress(source_file)
        self.progress_changed.emit(progress)

    # --- Add/remove detections ---
    def add_detection(
        self,
        source_file: str,
        frame_number: int,
        xc: float,
        yc: float,
        width: float,
        height: float,
        label: str,
        timestamp: float = 0.0,
    ) -> ValidatedDetection:
        """
        Add a new detection manually.

        Creates a synthetic Detection object and wraps it in a 
        ValidatedDetection with CONFIRMED status and is_manual=True. The
        detection is indexed into all lookup structures and the detection_added
        signal is emitted so the table can insert a row.

        Args:
            source_file: The video this detection belongs to.
            frame_number: The frame number where the detection is.
            xc, yc: Centre coordinates of the bounding box (in frame
                pixel coordinates).
            width, height: Bounding box dimensions in pixels.
            label: Class label - must be one of self._labels.
            timestamp: Timestamp in seconds. If the caller has access
                to the video metadata, pass frame_number / fps.
                Otherwise defaults to 0.0.
        
        Returns:
            The newly created ValidatedDetection.
        """
        if label not in self._labels:
            raise ValueError(
                f"Unknown label: {label}. "
                f"Valid labels are: {sorted(self._labels)}"
            )


        det = Detection(
            source_file=source_file,
            frame_number=frame_number,
            xc=xc,
            yc=yc,
            width=width,
            height=height,
            timestamp=timestamp,
            confidence=None,
            label=label,
            track_id=None,
        )

        vd = ValidatedDetection(
            detection=det,
            status=ValidationStatus.CONFIRMED,
            id=self._next_id,
            is_manual=True,
        )

        self._index_detection(vd)
        self._next_id += 1

        self.detection_added.emit(vd)

        progress = self.get_progress(source_file)
        self.progress_changed.emit(progress)

        return vd
    
    def remove_detection(self, detection_id: int) -> bool:
        """
        Remove manually added detection entirely.

        Only works on detections where is_manual is True. Pipeline detections
        cannot be removed - they should be rejected instead because the
        rejection itself is useful to inform downstream systems that the
        detector produced a false positive at this location.

        Args:
            detection_id: The unique ID of the detection to remove.

        Returns:
            True if the detection was removed, False if it was a pipeline
            detection that cannot be removed.
        
            Raises:
                KeyError: If detection_id is not found.
        """
        vd = self._by_id[detection_id]

        if not vd.is_manual:
            return False

        # Remove from all indexes
        self._detections.remove(vd)
        del self._by_id[detection_id]

        source_file = vd.detection.source_file
        self._by_video[source_file].remove(vd)

        key = (source_file, vd.detection.frame_number)
        self._by_frame[key].remove(vd)
        if not self._by_frame[key]:  # Clean up empty frame entry
            del self._by_frame[key]

        self.detection_removed.emit(detection_id)

        progress = self.get_progress(source_file)
        self.progress_changed.emit(progress)

        return True
    
    def rename_label(self, old_label: str, new_label: str) -> int:
        """
        Rename a label aross all detections.

        Every detection (Pipeline and manual) that has 'old_label' gets
        'new_label'. The label set is updated accordingly.

        Args:
            old_label: The label to replace.
            new_label: The new label name.

        Returns:
            The number of detections that were updated.

        Raises:
            ValueError: If old_label doesn't exist in the label set
        """
        if old_label not in self._labels:
            raise ValueError(f"Label '{old_label}' not found")

        count = 0
        for vd in self._detections:
            if vd.detection.label == old_label:
                vd.detection.label = new_label
                count += 1

        # Update the label set
        self._labels.discard(old_label)
        self._labels.add(new_label)

        return count

    def get_next_unreviewed(
        self, source_file: str, after_id: int = -1
    ) -> ValidatedDetection | None:
        """
        Fien the next unreviewed detection for a video, after a given ID.

        "Unreviewed means status is PENDING. The search is linear through the
        video's detections in frame order.

        Args:
            source_file: The video to search within.
            after_id: STart searching after this detectio ID. Use -1 to search
                from the beginning.

        Returns:
            The next PENDING ValidatedDetection, or None if all are reviewed.
        """

        detections = self.get_detections_for_video(source_file)

        past_start = (after_id == -1)

        for vd in detections:
            if not past_start:
                if vd.id == after_id:
                    past_start = True
                continue

            if vd.status == ValidationStatus.PENDING:
                return vd
            
        # Wrap around: check from the begininng up to after_id
        if after_id != -1:
            for vd in detections:
                if vd.id == after_id:
                    break

                if vd.status == ValidationStatus.PENDING:
                    return vd
                
        return None
    
    def set_corrected_geometry(
        self,
        detection_id: int,
        xc: float,
        yc: float,
        width: float,
        height: float,
    ) -> None:
        """
        Store corrected bounding box geometry for a detection.

        Automatically sets the status to CORRECTED. This method is called by the
        bounding box editing UI.
        """
        vd = self._by_id[detection_id]
        vd.corrected_geometry = {
            "xc": xc,
            "yc": yc,
            "width": width,
            "height": height,
        }
        vd.status = ValidationStatus.CORRECTED

        self.detection_status_changed.emit(detection_id, vd.status)

        source_file = vd.detection.source_file
        progress = self.get_progress(source_file)
        self.progress_changed.emit(progress)

    def undo_correction(self, detection_id: int) -> bool:
        """
        Revert a corrected detection to its original pipeline geometry.

        Clears the corrected_geometry dict and resets the status to PENDING
        (the reviewer hasn't confirmed or rejected the original geometry).

        Args:
            detection_id: The unique ID of the detection to revert.

        Returns:
            True if the detection had a correction that was rverted.
            False if there was nothing to undo.
        """
        vd = self._by_id.get(detection_id)

        if vd is None:
            return False
        
        if vd.corrected_geometry is None:
            return False
        
        vd.corrected_geometry = None
        vd.status = ValidationStatus.PENDING

        self.detection_status_changed.emit(detection_id, vd.status)

        source_file = vd.detection.source_file
        self.progress_changed.emit(self.get_progress(source_file))

        return True

    # --- Convenience propoerties ---
    @property
    def all_detections(self) -> list[ValidatedDetection]:
        """Return a flat list of all validated detections."""
        return self._detections
    
    @property
    def labels(self) -> set[str]:
        """
        All unique detection labels discovered in the datset.

        This is the authoritative set of valid labels for the session. Populated
        once during construction from the CSV. Manual detections must use a
        label from this set (TODO: Add functionality to modify the set).
        """
        return self._labels

    def get_by_id(self, detection_id: int) -> ValidatedDetection | None:
        """Look up a detection by its' uniwue ID."""
        return self._by_id.get(detection_id)
