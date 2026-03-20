"""
Session manager for save/load/export of validation state.

This module is intentionally free of Qt dependcies. It operates on the
ValidationModel's data and produces/consumes files. The Qt-side integration
(file dialogs, status bar updates) lives in tab.py and main_window.py.
"""

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from seavision.gui.validation.validation_model import (
    ValidatedDetection,
    ValidationModel,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


def _serialise_manual_detection(
    vd: ValidatedDetection,
) -> dict[str, Any]:
    """
    Serialise a manually added detection to a JSON-friendly dict.

    Manual detections need their full geometry and label stored because they
    don't exist in the CSV. Pipeline detections only need their status stored
    because the CSV provides the rest.
    """
    det = vd.detection
    return {
        "source_file": det.source_file,
        "frame_number": det.frame_number,
        "timestamp": det.timestamp,
        "xc": det.xc,
        "yc": det.yc,
        "width": det.width,
        "height": det.height,
        "label": det.label or "",
        "status": vd.status.name,
        "corrected_geometry": vd.corrected_geometry,
    }


class SessionManager:
    """
    Handles save, load, and export operations for validation sessions.

    All methods are stateless class-level operations - the manager does not hold
    a reference to the model or remember previous save paths. State tracking
    (current save path, unsaved changes flag) lives on the ValidationTab.

    File format:
        Session files use the .seavision-session extension and contain JSON with
        this structure:
        {
            "version": 1,
            "csv_path": "/path/to/detections.csv",
            "video_dir": "/path/to/videos/",
            "timestamp": "2025-06-15T14:30:00Z",
            "decisions": {
                "video.ts::47::0": {
                    "status": "CONFIRMED",
                    "corrected_geometry": null,
                    "is_manual": false
                },
                ...
            },
            "manual_detections": [
                {
                    "source_file": "video.ts",
                    "frame_number": 52,
                    "xc": 320.0, "yc": 240.0,
                    "width": 60.0, "height": 60.0,
                    "label": "seal",
                    "status": "CONFIRMED"
                },
                ...
            ]
        }

    Decision keys use the format "{source_file}::{frame_number}::{index}" where
    index is the detection's position within its frame. This is deterministic
    for a given CSV because CSVDetectionLoader loads in file order.
    """

    @staticmethod
    def save_session(
        path: Path | str,
        model: ValidationModel,
        csv_path: str,
        video_dir: str,
        aws_profile: str | None,
    ) -> None:
        """
        Save the current validation state to a .seavision-session JSON file.

        Args:
            path: Destination file path for the session file. Ends with
                .seavision-session.
            model: The ValidationModel containing all detection states.
            csv_path: Path to the detection CSV (stored for reload).
            video_dir: Path to the video directory (stored for reload).
            aws_profile: The AWS profile name to use for S3 operations.
        """
        path = Path(path)

        decisions: dict[str, dict[str, Any]] = {}
        manual_detections: list[dict[str, Any]] = {}

        for source_file in model.get_all_source_files():
            detections = model.get_detections_for_video(source_file)
            frame_counters: dict[int, int] = {}

            for vd in detections:
                if vd.is_manual:
                    manual_detections.append(
                        _serialise_manual_detection(vd),
                    )
                    continue
                
                frame_num = vd.detection.frame_number
                idx = frame_counters.get(frame_num, 0)
                frame_counters[frame_num] = idx + 1

                # Skip saving PENDING detectons - these can be read from CSV
                # on load
                if vd.status == ValidationStatus.PENDING:
                    continue

                key = f"{source_file}::{frame_num}::{idx}"
                decisions[key] = {
                    "status": vd.status.name,
                    "corrected_geometry": vd.corrected_geometry,
                    "is_manual": False,
                }

        session_data = {
            "version": 1,
            "csv_path": str(csv_path),
            "video_dir": str(video_dir),
            "aws_profile": aws_profile,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decisions": decisions,
            "manual_detections": manual_detections,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)
        
        logger.info("Session saved to %s (%d decisions, %d manual)",
                    path, len(decisions), len(manual_detections))
        
    
    @staticmethod
    def load_session(path: Path | str) -> dict[str, Any]:
        """
        Read and validate a session file.

        Returns the parsed JSON as a dict. Does NOT apply the state to a model - 
        that is the caller's responsibility.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file is not valid.
        """

        path = Path(path)

        # TODO: Add check that file extension is .seavision-session?

        with open(path, "r", encoding="utf-8") as f:
            try:
                data: dict = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Session file is not valid JSON: {e}"
                ) from e
            
        required = {"version", "csv_path", "video_dir", "decisions"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(
                f"Session file missing required keys: {missing}"
            )
        
        if data["version"] != 1:
            raise ValueError(
                f"Unsupported session version: {data['version']}. "
                f"This tool supports version 1."
            )

        data.setdefault("manual_detections", [])

        logger.info(
            "Loaded session from %s (%d decisions, %d manual)",
            path, len(data["decisions"]),
            len(data["manual_detections"]),
        )
        return data
    

    @staticmethod
    def apply_session_state(
        model: ValidationModel,
        session_data: dict[str, Any],
    ) -> dict[str, str]:
        """
        Apply saved decisions and manual detections to a live model.

        Called after the CSV has been re-loaded and the ValidationModel
        constructed with all detections in PENDING state.

        Returns:
            States dict: {"applied", "skipped", "manual_added"}
        """
        stats = {"applied": 0, "skipped": 0, "manual_added": 0}

        # build lookup keyed the same way as the session file
        model_keys: dict[str, ValidatedDetection] = {}
        for source_file in model.get_all_source_files():
            detections = model.get_detections_for_video(source_file)
            frame_counters: dict[int, int] = {}
            for vd in detections:
                if vd.is_manual:
                    continue
                frame_num = vd.detection.frame_number
                idx = frame_counters.get(frame_num, 0)
                frame_counters[frame_num] = idx + 1
                key = f"{source_file}::{frame_num}::{idx}"
                model_keys[key] = vd

        for key, decision in session_data["decisions"].items():
            vd = model_keys.get(key)
            if vd is None:
                logger.warning("Session key not found in model: %s", key)
                stats["skipped"] += 1
                continue
            
            try:
                status = ValidationStatus[decision["status"]]
            except KeyError:
                logger.warning(
                    "Unknown status '%s' for key %s",
                    decision["status"], key,
                )
                stats["skipped"] += 1
                continue

            model.set_status(vd.id, status)

            if decision.get("corrected_geometry") is not None:
                geom = decision["corrected_geometry"]
                model.set_corrected_geometry(
                    vd.id, geom["xc"], geom["yc"],
                    geom["width"], geom["height"],
                )

            stats["applied"] += 1

        # restore manual detections
        for manual in session_data.get("manual_detections", []):
            try:
                model.add_detection(
                    source_file=manual["source_file"],
                    frame_number=manual["frame_number"],
                    xc=manual["xc"], yc=manual["yc"],
                    width=manual["width"], height=manual["height"],
                    label=manual["label"],
                    timestamp=manual.get("timestamp", 0.0),
                )

                saved_status = ValidationStatus[manual.get(
                    "status", "CONFIRMED"
                )]
                if saved_status != ValidationStatus.CONFIRMED:
                    all_dets = model.get_detections_for_video(
                        manual["source_file"]
                    )
                    last_manual = all_dets[-1]
                    model.set_status(last_manual.id, saved_status)

                stats["manual_added"] += 1

            except (ValueError, KeyError) as e:
                logger.warning(
                    "Failed to restore manual detection: %s", e
                )
                stats["skipped"] += 1

        logger.info(
            "Applied session state: %d applied, %d skipped, "
            "%d manual restored",
            stats["applied"], stats["skipped"], stats["manual_added"],
        )
        return stats 


    @staticmethod
    def export_detections(
        path: Path | str,
        model: ValidationModel,
    ) -> int:
        """
        Export confirmed and corrected detections to a CSV file.

        Only CONFIRMED and CORRECTED detections are included. Adds
        'status' and 'source' columns to distinguish pipeline from
        manual detections. Uses corrected geometry where available.

        Returns:
            Number of detections written.
        """
        path = Path(path)
        exportable = {
            ValidationStatus.CONFIRMED, ValidationStatus.CORRECTED
        }

        fieldnames = [
            "source_file", "frame_number", "timestamp",
            "xc", "yc", "width", "height",
            "confidence", "label", "track_id",
            "status", "source",
        ]

        count = 0
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for source_file in model.get_all_source_files():
                for vd in model.get_detections_for_video(source_file):
                    if vd.status not in exportable:
                        continue

                    det = vd.detection
                    if vd.corrected_geometry is not None:
                        geom = vd.corrected_geometry
                        xc, yc = geom["xc"], geom["yc"]
                        width, height = geom["width"], geom["height"]
                    else:
                        xc, yc = det.xc, det.yc
                        width, height = det.width, det.height

                    writer.writerow({
                        "source_file": det.source_file,
                        "frame_number": det.frame_number,
                        "timestamp": det.timestamp,
                        "xc": xc, "yc": yc,
                        "width": width, "height": height,
                        "confidence": (
                            det.confidence if det.confidence is not None
                            else ""
                        ),
                        "label": det.label or "",
                        "track_id": (
                            det.track_id if det.track_id is not None
                            else ""
                        ),
                        "status": vd.status.name,
                        "source": "manual" if vd.is_manual else "pipeline",
                    })
                    count += 1

        logger.info("Exported %d detections to %s", count, path)
        return count
