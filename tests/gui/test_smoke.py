"""
Automated smoke tests for the GUI's non-visual logic.
 
Run with: pytest tests/gui/test_smoke.py -v
 
These tests verify the critical data paths without requiring a visible
window or manual interaction. They complement the manual smoke test
checklist in docs/gui/smoke-test.md.
"""
 
import csv
import json
from pathlib import Path
 
import pytest
from PySide6.QtWidgets import QApplication
 
from seavision.engine.detectors.base import Detection
from seavision.gui.validation.validation_model import (
    ValidationModel,
    ValidationStatus,
)
from seavision.gui.validation.session import SessionManager
 
 
# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
 
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
 
 
def _make_detection(source_file, frame, confidence=0.5, label="motion"):
    return Detection(
        source_file=source_file,
        timestamp=frame / 10.0,
        frame_number=frame,
        xc=100.0, yc=100.0,
        width=50.0, height=50.0,
        confidence=confidence,
        label=label,
    )
 
 
class _FakeSource:

    def __init__(self, detections):
        self._detections = detections
        self._by_frame = {}
        for d in detections:
            self._by_frame.setdefault(d.frame_number, []).append(d)

    def get_frame_numbers_with_detections(self, source_file=None):
        if source_file:
            return sorted(set(
                d.frame_number for d in self._detections
                if d.source_file == source_file
            ))
        return sorted(self._by_frame.keys())

    def get_detections_for_frame(self, frame_number):
        return self._by_frame.get(frame_number, [])

    def get_source_files(self):
        return sorted(set(d.source_file for d in self._detections))

    def get_all_detections(self):
        return list(self._detections)
 
 
@pytest.fixture
def sample_detections():
    return [
        _make_detection("vid1.ts", 10, 0.9, "seal"),
        _make_detection("vid1.ts", 20, 0.3, "motion"),
        _make_detection("vid1.ts", 20, 0.7, "seal"),
        _make_detection("vid2.ts", 5, 0.5, "motion"),
        _make_detection("vid2.ts", 15, 0.8, "seal"),
    ]
 
 
@pytest.fixture
def model(qapp, sample_detections):
    return ValidationModel(_FakeSource(sample_detections))
 
 
# ---------------------------------------------------------------------------
# Smoke: ValidationModel core operations
# ---------------------------------------------------------------------------
 
class TestModelSmoke:
 
    def test_initial_state_all_pending(self, model):
        for vd in model.all_detections:
            assert vd.status == ValidationStatus.PENDING
 
    def test_confirm_changes_status(self, model):
        det = model.all_detections[0]
        model.set_status(det.id, ValidationStatus.CONFIRMED)
        assert model.all_detections[0].status == ValidationStatus.CONFIRMED
 
    def test_reject_changes_status(self, model):
        det = model.all_detections[1]
        model.set_status(det.id, ValidationStatus.REJECTED)
        assert model.all_detections[1].status == ValidationStatus.REJECTED
 
    def test_progress_counts(self, model):
        # Get detections for a specific video to avoid ordering assumptions
        vid1_dets = model.get_detections_for_video("vid1.ts")
        model.set_status(vid1_dets[0].id, ValidationStatus.CONFIRMED)
        model.set_status(vid1_dets[1].id, ValidationStatus.REJECTED)
        progress = model.get_progress("vid1.ts")
        assert progress["confirmed"] == 1
        assert progress["rejected"] == 1
        assert progress["total"] == 3
        assert progress["reviewed"] == 2
    
    def test_get_next_unreviewed_skips_reviewed(self, model):
        vid1_dets = model.get_detections_for_video("vid1.ts")
        model.set_status(vid1_dets[0].id, ValidationStatus.CONFIRMED)
        nxt = model.get_next_unreviewed("vid1.ts", after_id=vid1_dets[0].id)
        assert nxt is not None
        assert nxt.id != vid1_dets[0].id

    def test_get_next_unreviewed_none_when_all_done(self, model):
        for vd in model.get_detections_for_video("vid1.ts"):
            model.set_status(vd.id, ValidationStatus.CONFIRMED)
        assert model.get_next_unreviewed("vid1.ts") is None

    def test_corrected_geometry(self, model):
        det = model.all_detections[0]
        model.set_corrected_geometry(det.id, 200.0, 150.0, 80.0, 60.0)
        updated = model.all_detections[0]
        assert updated.status == ValidationStatus.CORRECTED
        assert updated.corrected_geometry["xc"] == 200.0

    def test_add_manual_detection(self, model):
        before = len(model.all_detections)
        model.add_detection(
            source_file="vid1.ts", frame_number=99,
            xc=300.0, yc=300.0, width=60.0, height=60.0,
            label="seal",
        )
        assert len(model.all_detections) == before + 1
        added = model.all_detections[-1]
        assert added.is_manual
        assert added.status == ValidationStatus.CONFIRMED

    def test_remove_manual_detection(self, model):
        model.add_detection(
            source_file="vid1.ts", frame_number=99,
            xc=300.0, yc=300.0, width=60.0, height=60.0,
            label="seal",
        )
        added = model.all_detections[-1]
        model.remove_detection(added.id)
        assert all(vd.id != added.id for vd in model.all_detections)

    def test_cannot_remove_pipeline_detection(self, model):
        det = model.all_detections[0]
        assert model.remove_detection(det.id) is False

    def test_filter_by_video(self, model):
        vid1_dets = model.get_detections_for_video("vid1.ts")
        vid2_dets = model.get_detections_for_video("vid2.ts")
        assert len(vid1_dets) == 3
        assert len(vid2_dets) == 2

 
# ---------------------------------------------------------------------------
# Smoke: Session save/load/export round-trip
# ---------------------------------------------------------------------------
 
class TestSessionSmoke:
 
    def test_save_and_load_round_trip(self, tmp_path, model):
        dets = model.all_detections
        model.set_status(dets[0].id, ValidationStatus.CONFIRMED)
        model.set_status(dets[1].id, ValidationStatus.REJECTED)
        model.set_corrected_geometry(dets[2].id, 999.0, 888.0, 77.0, 66.0)
 
        path = tmp_path / "test.seavision-session"
        SessionManager.save_session(path, model, "test.csv", "/videos", aws_profile=None)
 
        data = SessionManager.load_session(path)
        assert data["version"] == 1
        assert data["csv_path"] == "test.csv"
        assert len(data["decisions"]) == 3  # 1 confirmed + 1 rejected + 1 corrected
 
    def test_apply_restores_statuses(self, tmp_path, qapp, sample_detections):
        source = _FakeSource(sample_detections)
        model = ValidationModel(source)
        dets = model.all_detections
        model.set_status(dets[0].id, ValidationStatus.CONFIRMED)
        model.set_status(dets[1].id, ValidationStatus.REJECTED)
 
        path = tmp_path / "test.seavision-session"
        SessionManager.save_session(path, model, "test.csv", "/videos", aws_profile=None)
 
        session_data = SessionManager.load_session(path)
        fresh = ValidationModel(_FakeSource(sample_detections))
        stats = SessionManager.apply_session_state(fresh, session_data)
        assert stats["applied"] == 2
 
        fd = fresh.all_detections
        assert fd[0].status == ValidationStatus.CONFIRMED
        assert fd[1].status == ValidationStatus.REJECTED
        assert fd[2].status == ValidationStatus.PENDING
 
    def test_export_only_confirmed(self, tmp_path, model):
        dets = model.all_detections
        model.set_status(dets[0].id, ValidationStatus.CONFIRMED)
        model.set_status(dets[1].id, ValidationStatus.REJECTED)
 
        path = tmp_path / "export.csv"
        count = SessionManager.export_detections(path, model)
        assert count == 1
 
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["status"] == "CONFIRMED"
 
    def test_export_uses_corrected_geometry(self, tmp_path, model):
        det = model.all_detections[0]
        model.set_corrected_geometry(det.id, 999.0, 888.0, 77.0, 66.0)
 
        path = tmp_path / "export.csv"
        SessionManager.export_detections(path, model)
 
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert float(rows[0]["xc"]) == 999.0
        assert rows[0]["status"] == "CORRECTED"
 
    def test_manual_detections_in_session(self, tmp_path, model):
        model.add_detection(
            source_file="vid1.ts", frame_number=99,
            xc=300.0, yc=300.0, width=60.0, height=60.0,
            label="seal",
        )
 
        path = tmp_path / "test.seavision-session"
        SessionManager.save_session(path, model, "test.csv", "/videos", aws_profile=None)
 
        data = json.loads(path.read_text())
        assert len(data["manual_detections"]) == 1
        assert data["manual_detections"][0]["label"] == "seal"
 
    def test_pending_not_saved(self, tmp_path, model):
        """PENDING detections must not appear in the session file."""
        path = tmp_path / "test.seavision-session"
        SessionManager.save_session(path, model, "test.csv", "/videos", aws_profile=None)
 
        data = json.loads(path.read_text())
        assert len(data["decisions"]) == 0  # All pending, none saved