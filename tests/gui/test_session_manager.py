"""Tests for the session manager (save/load/export)."""

import csv
import json
from pathlib import Path

import pytest

from seavision.engine.detectors.base import Detection
from seavision.gui.validation.validation_model import (
    ValidatedDetection,
    ValidationModel,
    ValidationStatus,
)
from seavision.gui.validation.session import SessionManager


class _FakeDetectionSource:
    """Minimal detection source for testing."""

    def __init__(self, detections: list[Detection]):
        self._by_frame: dict[int, list[Detection]] = {}
        for det in detections:
            self._by_frame.setdefault(det.frame_number, []).append(det)

    def get_frame_numbers_with_detections(self) -> list[int]:
        return sorted(self._by_frame.keys())

    def get_detections_for_frame(self, frame_number: int) -> list[Detection]:
        return self._by_frame.get(frame_number, [])
    

def _make_detections(count: int = 5, source_file: str = "video.ts"):
    return [
        Detection(
            source_file=source_file,
            timestamp=float(i),
            frame_number=i * 10,
            xc=100.0 + i, yc=200.0 + i,
            width=50.0, height=50.0,
            confidence=0.8 + i * 0.02,
            label="seal" if i % 2 == 0 else "bird",
        )
        for i in range(count)
    ]

@pytest.fixture
def sample_detections():
    return _make_detections()

@pytest.fixture
def model_with_detections(qapp, sample_detections):
    source = _FakeDetectionSource(sample_detections)
    return ValidationModel(source)


class TestSessionSaveLoad:

    def test_save_creates_valid_json(self, tmp_path, model_with_detections):
        path = tmp_path / "test.seavision-session"
        SessionManager.save_session(
            path, model_with_detections, "/csv/path.csv", "/video/dir",
            aws_profile="default",
        )
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["version"] == 1
        assert data["csv_path"] == "/csv/path.csv"
        assert data["video_dir"] == "/video/dir"
        assert "decisions" in data

    def test_round_trip_preserves_statuses(
        self, tmp_path, qapp, sample_detections
    ):
        source = _FakeDetectionSource(sample_detections)
        model = ValidationModel(source)
        all_dets = model.all_detections
        model.set_status(all_dets[0].id, ValidationStatus.CONFIRMED)
        model.set_status(all_dets[1].id, ValidationStatus.REJECTED)
        model.set_status(all_dets[2].id, ValidationStatus.SKIPPED)

        path = tmp_path / "test.seavision-session"
        SessionManager.save_session(path, model, "test.csv", "/videos",
                                    aws_profile="default")

        session_data = SessionManager.load_session(path)
        fresh_model = ValidationModel(_FakeDetectionSource(sample_detections))
        stats = SessionManager.apply_session_state(fresh_model, session_data)

        assert stats["applied"] == 3
        fresh_dets = fresh_model.all_detections
        assert fresh_dets[0].status == ValidationStatus.CONFIRMED
        assert fresh_dets[1].status == ValidationStatus.REJECTED
        assert fresh_dets[2].status == ValidationStatus.SKIPPED
        assert fresh_dets[3].status == ValidationStatus.PENDING

    def test_load_with_extra_keys_skips(
        self, tmp_path, qapp, sample_detections
    ):
        source = _FakeDetectionSource(sample_detections)
        model = ValidationModel(source)
        model.set_status(model.all_detections[0].id, ValidationStatus.CONFIRMED)

        path = tmp_path / "test.seavision-session"
        SessionManager.save_session(path, model, "test.csv", "/videos",
                                    aws_profile="default")

        data = json.loads(path.read_text())
        data["decisions"]["nonexistent.ts::999::0"] = {
            "status": "CONFIRMED", "corrected_geometry": None,
            "is_manual": False,
        }
        path.write_text(json.dumps(data))

        session_data = SessionManager.load_session(path)
        fresh_model = ValidationModel(_FakeDetectionSource(sample_detections))
        stats = SessionManager.apply_session_state(fresh_model, session_data)
        assert stats["applied"] == 1
        assert stats["skipped"] == 1

    def test_load_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SessionManager.load_session(tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.seavision-session"
        path.write_text("not json{{{")
        with pytest.raises(ValueError, match="not valid JSON"):
            SessionManager.load_session(path)

    def test_load_missing_keys_raises(self, tmp_path):
        path = tmp_path / "incomplete.seavision-session"
        path.write_text(json.dumps({"version": 1}))
        with pytest.raises(ValueError, match="missing required keys"):
            SessionManager.load_session(path)


class TestSessionExport:

    def test_export_writes_correct_columns(
        self, tmp_path, model_with_detections
    ):
        model = model_with_detections
        model.set_status(
            model.all_detections[0].id, ValidationStatus.CONFIRMED
        )
        path = tmp_path / "export.csv"
        count = SessionManager.export_detections(path, model)
        assert count == 1

        with open(path) as f:
            reader = csv.DictReader(f)
            assert "status" in reader.fieldnames
            assert "source" in reader.fieldnames
            rows = list(reader)
        assert rows[0]["status"] == "CONFIRMED"
        assert rows[0]["source"] == "pipeline"

    def test_export_only_confirmed_and_corrected(
        self, tmp_path, model_with_detections
    ):
        model = model_with_detections
        dets = model.all_detections
        model.set_status(dets[0].id, ValidationStatus.CONFIRMED)
        model.set_status(dets[1].id, ValidationStatus.REJECTED)

        path = tmp_path / "export.csv"
        count = SessionManager.export_detections(path, model)
        assert count == 1

    def test_export_with_corrected_geometry(
        self, tmp_path, model_with_detections
    ):
        model = model_with_detections
        model.set_corrected_geometry(
            model.all_detections[0].id, 999.0, 888.0, 77.0, 66.0
        )
        path = tmp_path / "export.csv"
        SessionManager.export_detections(path, model)

        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert float(rows[0]["xc"]) == 999.0
        assert rows[0]["status"] == "CORRECTED"

    def test_export_nothing_confirmed(
        self, tmp_path, model_with_detections
    ):
        path = tmp_path / "export.csv"
        count = SessionManager.export_detections(
            path, model_with_detections
        )
        assert count == 0
        with open(path) as f:
            reader = csv.DictReader(f)
            assert len(list(reader)) == 0
            assert "source_file" in reader.fieldnames

    def test_export_manual_marked(self, tmp_path, model_with_detections):
        model = model_with_detections
        model.add_detection(
            source_file="video.ts", frame_number=100,
            xc=300.0, yc=300.0, width=60.0, height=60.0,
            label="seal",
        )
        path = tmp_path / "export.csv"
        SessionManager.export_detections(path, model)

        with open(path) as f:
            rows = list(csv.DictReader(f))
        manual_rows = [r for r in rows if r["source"] == "manual"]
        assert len(manual_rows) == 1
        assert manual_rows[0]["confidence"] == ""
