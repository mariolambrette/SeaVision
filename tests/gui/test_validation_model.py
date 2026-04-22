"""
Tests for validation model - the core data layer of the review workflow.

These tests verify status changes, singal emissions, progress counting, next-
unreviewed navigation, and manual detection add/remove.
"""

import pytest

from seavision.engine.detectors.base import Detection
from seavision.gui.validation.validation_model import ValidationModel



class _FakeDetectionSource:
    """
    Minimal stand-in for CSVDetectionLoader, built from a list of Detection
    objects. Provides the same query interface that ValidationModel expects.
    """

    def __init__(self, detections: list[Detection]):
        self._detections = list(detections)

        self._by_source: dict[str, list[Detection]] = {}
        self._by_frame: dict[tuple[str, int], list[Detection]] = {}

        for det in detections:
            self._by_source.setdefault(det.source_file, []).append(det)
            key = (det.source_file, det.frame_number)
            self._by_frame.setdefault(key, []).append(det)

    
    @property
    def sources_in_file(self) -> list[str]:
        return list(self._by_source.keys())

    @property
    def detections(self) -> list[Detection]:
        return self._detections

    def get_frame_numbers_with_detections(
        self, source_file: str = None
    ) -> list[int]:
        
        if source_file is not None:
            dets = self._by_source.get(source_file, [])
        else:
            dets = self._detections
        return sorted({d.frame_number for d in dets})

    def get_detections_for_frame(
        self, frame_number: int, source_file: str = None
    ) -> list[Detection]:
        if source_file is not None:
            return self._by_frame.get(
                (source_file, frame_number), []
            )
        return [
            d for d in self._detections
            if d.frame_number == frame_number
        ]
    

class TestValidationModelInitialState:
    """Verify the model contructs correctly from sample detections."""

    def test_all_start_pending(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        for vd in model.all_detections:
            assert vd.status == ValidationStatus.PENDING

    def test_none_are_manual(self, qapp, sample_detections):
        model = self._make_model(sample_detections)
        for vd in model.all_detections:
            assert vd.is_manual is False

    def test_ids_are_sequential(self, qapp, sample_detections):
        model = self._make_model(sample_detections)
        ids = [vd.id for vd in model.all_detections]
        assert ids == list(range(len(sample_detections)))

    def test_total_count_matched(self, qapp, sample_detections):
        model = self._make_model(sample_detections)
        assert len(model.all_detections) == len(sample_detections)

    def test_get_all_source_files(self, qapp, sample_detections):
        model = self._make_model(sample_detections)
        sources = model.get_all_source_files()
        expected = {det.source_file for det in sample_detections}
        assert set(sources) == expected

    def test_get_detections_for_video(self, qapp, sample_detections):
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        expected_count = sum(
            1 for d in sample_detections if d.source_file == source
        )
        result = model.get_detections_for_video(source)
        assert len(result) == expected_count

    def test_get_detections_for_frame(self, qapp, sample_detections):
        model = self._make_model(sample_detections)
        det = sample_detections[0]
        result = model.get_detections_for_frame(
            det.source_file, det.frame_number
        )
        assert len(result) >= 1
        assert all(
            vd.detection.frame_number == det.frame_number for vd in result
        )

    def test_add_detection_rejects_unknown_label(
        self, qapp, sample_detections
    ):
        """Adding a detection with unknown label should raise ValueError."""
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file

        with pytest.raises(ValueError, match="Unknown label"):
            model.add_detection(
                source_file=source, frame_number=10,
                xc=100.0, yc=100.0, width=30.0, height=30.0,
                label="FAKE_LABEL"
            )

    @staticmethod
    def _make_model(detections):
        from seavision.gui.validation.validation_model import ValidationModel
        return ValidationModel(_FakeDetectionSource(detections))
    

class TestValidationModelStatusChanges:
    """Verify that set_status updates state and emits signals."""

    def test_set_status_changes_detection(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        det_id = model.all_detections[0].id
        model.set_status(det_id, ValidationStatus.CONFIRMED)
        assert model.get_by_id(det_id).status == ValidationStatus.CONFIRMED

    def test_set_status_emits_detection_changed(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        received = []
        model.detection_status_changed.connect(
            lambda id_, status: received.append((id_, status))
        )
        det_id = model.all_detections[0].id
        model.set_status(det_id, ValidationStatus.REJECTED)
        assert len(received) == 1
        assert received[0] == (det_id, ValidationStatus.REJECTED)

    def test_set_status_emits_progress_changed(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        received = []
        model.progress_changed.connect(lambda p: received.append(p))
        det_id = model.all_detections[0].id
        model.set_status(det_id, ValidationStatus.CONFIRMED)
        assert len(received) == 1
        assert received[0]["confirmed"] == 1 

    def test_unknown_id_raises_key_error(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        import pytest
        model = self._make_model(sample_detections)
        with pytest.raises(KeyError):
            model.set_status(99999, ValidationStatus.CONFIRMED)

    @staticmethod
    def _make_model(detections):
        from seavision.gui.validation.validation_model import ValidationModel
        return ValidationModel(_FakeDetectionSource(detections))


class TestValidationModelProgress:
    """Verify progress counting is accurate."""

    def test_initial_progress_all_pending(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        progress = model.get_progress(source)
        video_count = sum(
            1 for d in sample_detections if d.source_file == source
        )
        assert progress["pending"] == video_count
        assert progress["confirmed"] == 0
        assert progress["reviewed"] == 0
        assert progress["manual"] == 0

    def test_progress_after_mixed_reviews(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        video_dets = model.get_detections_for_video(source)
        model.set_status(video_dets[0].id, ValidationStatus.CONFIRMED)
        model.set_status(video_dets[1].id, ValidationStatus.CONFIRMED)
        if len(video_dets) > 2:
            model.set_status(video_dets[2].id, ValidationStatus.REJECTED)
        progress = model.get_progress(source)
        assert progress["confirmed"] == 2
        assert progress["rejected"] == (1 if len(video_dets) > 2 else 0)

    def test_progress_includes_manual_count(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        model.add_detection(
            source_file=source, frame_number=10,
            xc=100.0, yc=100.0, width=40.0, height=40.0,
            label="fish"
        )
        progress = model.get_progress(source)
        assert progress["manual"] == 1
        assert progress["confirmed"] >= 1

    @staticmethod
    def _make_model(detections):
        from seavision.gui.validation.validation_model import ValidationModel
        return ValidationModel(_FakeDetectionSource(detections))
    

class TestValidationModelNextUnreviewed:
    """Verify the get_next_unreviewed navigation logic."""

    def test_returns_first_pending(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        result = model.get_next_unreviewed(source)
        assert result is not None
        video_dets = model.get_detections_for_video(source)
        assert result.id == video_dets[0].id

    def test_skips_reviewed_detections(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        video_dets = model.get_detections_for_video(source)
        model.set_status(video_dets[0].id, ValidationStatus.CONFIRMED)
        result = model.get_next_unreviewed(source, after_id=video_dets[0].id)
        assert result is not None
        assert result.id == video_dets[1].id

    def test_returns_none_when_all_reviewed(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        for vd in model.get_detections_for_video(source):
            model.set_status(vd.id, ValidationStatus.CONFIRMED)
        assert model.get_next_unreviewed(source) is None

    def test_wraps_around_to_find_pending(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        video_dets = model.get_detections_for_video(source)
        if len(video_dets) >= 3:
            for vd in video_dets[1:]:
                model.set_status(vd.id, ValidationStatus.CONFIRMED)
            last_id = video_dets[-1].id
            result = model.get_next_unreviewed(source, after_id=last_id)
            assert result is not None
            assert result.id == video_dets[0].id

    def test_skips_manual_additions(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        video_dets = model.get_detections_for_video(source)
        model.set_status(video_dets[0].id, ValidationStatus.CONFIRMED)
        model.add_detection(
            source_file=source,
            frame_number=video_dets[0].detection.frame_number,
            xc=200.0, yc=200.0, width=30.0, height=30.0,
            label="fish"
        )
        result = model.get_next_unreviewed(source, after_id=video_dets[0].id)
        assert result is not None
        assert result.is_manual is False
        assert result.status == ValidationStatus.PENDING

    @staticmethod
    def _make_model(detections):
        from seavision.gui.validation.validation_model import ValidationModel
        return ValidationModel(_FakeDetectionSource(detections))
    

class TestValidationModelManualDetections:
    """Verify adding and removing manual detections."""

    def test_add_detection_creates_validated_detection(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import (
            ValidationModel, ValidationStatus,
        )
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        original_count = len(model.all_detections)
        vd = model.add_detection(
            source_file=source, frame_number=99,
            xc=320.0, yc=240.0, width=50.0, height=40.0,
            label="fish"
        )
        assert vd.is_manual is True
        assert vd.status == ValidationStatus.CONFIRMED
        assert vd.detection.frame_number == 99
        assert vd.detection.xc == 320.0
        assert vd.detection.label == "fish"
        assert vd.detection.confidence is None
        assert len(model.all_detections) == original_count + 1

    def test_add_detection_assigns_unique_id(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        vd1 = model.add_detection(
            source_file=source, frame_number=10,
            xc=100.0, yc=100.0, width=30.0, height=30.0,
            label="fish"
        )
        vd2 = model.add_detection(
            source_file=source, frame_number=10,
            xc=200.0, yc=200.0, width=30.0, height=30.0,
            label="fish"
        )
        assert vd1.id != vd2.id
        assert vd1.id == len(sample_detections)
        assert vd2.id == len(sample_detections) + 1

    def test_add_detection_emits_detection_added(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        received = []
        model.detection_added.connect(lambda vd: received.append(vd))
        source = sample_detections[0].source_file
        vd = model.add_detection(
            source_file=source, frame_number=10,
            xc=100.0, yc=100.0, width=30.0, height=30.0,
            label="fish"
        )
        assert len(received) == 1
        assert received[0].id == vd.id

    def test_add_detection_emits_progress_changed(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        received = []
        model.progress_changed.connect(lambda p: received.append(p))
        source = sample_detections[0].source_file
        model.add_detection(
            source_file=source, frame_number=10,
            xc=100.0, yc=100.0, width=30.0, height=30.0,
            label="fish"
        )
        assert len(received) == 1
        assert received[0]["manual"] == 1

    def test_added_detection_appears_in_frame_lookup(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        model.add_detection(
            source_file=source, frame_number=999,
            xc=100.0, yc=100.0, width=30.0, height=30.0,
            label="fish"
        )
        result = model.get_detections_for_frame(source, 999)
        assert len(result) == 1
        assert result[0].is_manual is True

    def test_remove_manual_detection(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        original_count = len(model.all_detections)
        vd = model.add_detection(
            source_file=source, frame_number=999,
            xc=100.0, yc=100.0, width=30.0, height=30.0,
            label="fish"
        )
        assert len(model.all_detections) == original_count + 1
        result = model.remove_detection(vd.id)
        assert result is True
        assert len(model.all_detections) == original_count
        assert model.get_by_id(vd.id) is None
        assert model.get_detections_for_frame(source, 999) == []

    def test_remove_pipeline_detection_returns_false(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        pipeline_id = model.all_detections[0].id
        result = model.remove_detection(pipeline_id)
        assert result is False
        assert model.get_by_id(pipeline_id) is not None

    def test_remove_emits_detection_removed(self, qapp, sample_detections):
        from seavision.gui.validation.validation_model import ValidationModel
        model = self._make_model(sample_detections)
        source = sample_detections[0].source_file
        vd = model.add_detection(
            source_file=source, frame_number=10,
            xc=100.0, yc=100.0, width=30.0, height=30.0,
            label="fish"
        )
        received = []
        model.detection_removed.connect(lambda id_: received.append(id_))
        model.remove_detection(vd.id)
        assert len(received) == 1
        assert received[0] == vd.id

    @staticmethod
    def _make_model(detections):
        from seavision.gui.validation.validation_model import ValidationModel
        return ValidationModel(_FakeDetectionSource(detections))
