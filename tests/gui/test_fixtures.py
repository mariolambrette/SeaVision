"""
Smoke tests for the GUI test infrastructure.

Verify that pytest discovers this directory and the shared fixtures from
conftest.py work correctly.
"""

from seavision.engine.detectors.base import Detection

class TestQAppFixture:
    """Verify the QApplication fixture is available and functional."""

    def test_qapp_is_not_none(self, qapp):
        """The qapp fixture should return a live QApplication instance."""
        assert qapp is not None

    def test_qapp_is_qapplication(self, qapp):
        """The fixture should return a genuine QApplication."""
        from PySide6.QtWidgets import QApplication

        assert isinstance(qapp, QApplication)


class TestSampleDetectionsFixture:
    """Verify the sample_detections fixture provides usable test data."""

    def test_returns_list(self, sample_detections):
        """Fixture should return a plain list."""
        assert isinstance(sample_detections, list)

    def test_correct_count(self, sample_detections):
        """Fixture should return exactly 10 detections."""
        assert len(sample_detections) == 10

    def test_all_are_detections(self, sample_detections):
        """Every item should be an engine Detection dataclass."""
        for det in sample_detections:
            assert isinstance(det, Detection)

    def test_multiple_source_files(self, sample_detections):
        """Detections should span at least two different source videos."""
        sources = {det.source_file for det in sample_detections}
        assert len(sources) >= 2

    def test_multiple_frame_numbers(self, sample_detections):
        """Detections should cover multiple frame numbers."""
        frames = {det.frame_number for det in sample_detections}
        assert len(frames) >= 4

    def test_has_varied_confidence(self, sample_detections):
        """Confidence values should not all be the same."""
        confidences = {det.confidence for det in sample_detections}
        assert len(confidences) > 1

    def test_has_labels_and_tracks(self, sample_detections):
        """At least some detections should have labels and track IDs."""
        labels = {det.label for det in sample_detections if det.label}
        tracks = {
            det.track_id for det in sample_detections
            if det.track_id is not None
        }
        assert len(labels) >= 2
        assert len(tracks) >= 2

    def test_function_scoped_independence(self, sample_detections):
        """
        Mutating the fixture in one test should not affect another.
        Pop an item - the next test should still see all 10.
        """
        sample_detections.pop()
        assert len(sample_detections) == 9  # This test sees the mutation

    def test_function_scoped_fresh_copy(self, sample_detections):
        """After the previous test popped one, we should still get 10."""
        assert len(sample_detections) == 10


class TestSampleVideoPathFixture:
    """Verify the sample_video_path fixture behaves correctly."""

    def test_skips_when_no_video(self, sample_video_path):
        """
        If no test video exists, this test is automatically skipped.
        If a video does exist, confirm the path points to a real file.
        """
        assert sample_video_path.exists()
        assert sample_video_path.suffix == ".ts"
