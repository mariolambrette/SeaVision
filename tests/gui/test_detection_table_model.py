"""Tests for the DetectionTableModel."""

from pyexpat import model

from seavision.engine.detectors.base import Detection
from seavision.gui.validation.detection_table import (
    DetectionTableModel,
    COLUMNS,
)
from seavision.gui.validation.validation_model import (
    ValidatedDetection,
    ValidationStatus,
)


def _make_detection(
    frame: int = 10,
    confidence: float = 0.75,
    label: str = "fish",
    track_id: int = 1,
) -> Detection:
    """Create a Detection with sensible defaults for testing."""
    return Detection(
        source_file="test.ts",
        timestamp=frame / 10.0,
        frame_number=frame,
        xc=320.0,
        yc=240.0,
        width=100.0,
        height=80.0,
        confidence=confidence,
        label=label,
        track_id=track_id,
    )


def _wrap(detections: list[Detection]) -> list[ValidatedDetection]:
    """Wrap raw Detection objects in ValidatedDetection for testing."""
    return [
        ValidatedDetection(detection=det, id=i)
        for i, det in enumerate(detections)
    ]

class TestDetectionTableModel:
    """Test the detection table model's data interface."""

    def test_row_count_matches_detections(self, qapp, sample_detections):
        """rowCount should equal the number of detections set."""
        from seavision.gui.validation.detection_table import DetectionTableModel

        model = DetectionTableModel()
        model.set_detections(_wrap(sample_detections), fps=10.0)

        assert model.rowCount() == len(sample_detections)

    def test_column_count_matches_definition(self, qapp):
        """columnCount should match the COLUMNS definition."""
        from seavision.gui.validation.detection_table import (
            DetectionTableModel,
            COLUMNS,
        )
        model = DetectionTableModel()
        assert model.columnCount() == len(COLUMNS)

    def test_frame_column_displays_frame_number(self, qapp):
        """Column 0 (Frame) should show the frame number as a string."""
        from seavision.gui.validation.detection_table import DetectionTableModel
        from PySide6.QtCore import Qt

        model = DetectionTableModel()
        model.set_detections(_wrap([_make_detection(frame=47)]))

        index = model.index(0, 0)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "47"

    def test_time_column_formats_correctly(self, qapp):
        """Column 1 (Time) should format as M:SS.s."""
        from seavision.gui.validation.detection_table import DetectionTableModel
        from PySide6.QtCore import Qt

        model = DetectionTableModel()
        model.set_detections(_wrap([_make_detection(frame=47)]), fps=10)

        index = model.index(0, 1)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "0:04.7"

    def test_confidence_formats_two_decimals(self, qapp):
        """Column 2 (Confidence) should format to two decimal places."""
        from seavision.gui.validation.detection_table import DetectionTableModel
        from PySide6.QtCore import Qt

        model = DetectionTableModel()
        model.set_detections(_wrap([_make_detection(confidence=0.756)]))

        index = model.index(0, 2)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "0.76"

    def test_none_label_shows_dash(self, qapp):
        """Column 3 (Label) should show '—' if label is None."""
        from seavision.gui.validation.detection_table import DetectionTableModel
        from PySide6.QtCore import Qt

        model = DetectionTableModel()
        model.set_detections(_wrap([_make_detection(label=None)]))

        index = model.index(0, 3)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "—"

    def test_none_track_shows_dash(self, qapp):
        """Column 4 (Track) should show '—' if track_id is None."""
        from seavision.gui.validation.detection_table import DetectionTableModel
        from PySide6.QtCore import Qt

        model = DetectionTableModel()
        model.set_detections(_wrap([_make_detection(track_id=None)]))

        index = model.index(0, 4)
        assert model.data(index, Qt.ItemDataRole.DisplayRole) == "—"
        

    def test_header_data_returns_column_names(self, qapp):
        """Horizontal headers should return the column names."""
        from seavision.gui.validation.detection_table import DetectionTableModel
        from PySide6.QtCore import Qt
        
        model = DetectionTableModel()
        
        expected = ["Frame", "Time", "Confidence", "Label", "Track", "Status"]
        for i, name in enumerate(expected):
            assert model.headerData(
                i, 
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.DisplayRole
            ) == name
        
    def test_set_detections_updates_row_count(self, qapp):
        """Setting new detections should change rowCount."""
        from seavision.gui.validation.detection_table import DetectionTableModel

        model = DetectionTableModel()
        model.set_detections(_wrap([_make_detection(frame=1)]))
        assert model.rowCount() == 1

        model.set_detections(
            _wrap([_make_detection(frame=i) for i in range(10)])
        )
        assert model.rowCount() == 10

    def test_empty_set_detections(self, qapp):
        """Setting an empty list should give rowCount 0."""
        from seavision.gui.validation.detection_table import DetectionTableModel

        model = DetectionTableModel()
        model.set_detections(_wrap([_make_detection()]))
        model.set_detections([])

        assert model.rowCount() == 0

    def test_detection_at_valid_index(self, qapp, sample_detections):
        """detection_at should return the correct Detection."""
        from seavision.gui.validation.detection_table import DetectionTableModel

        model = DetectionTableModel()
        model.set_detections(_wrap(sample_detections), fps=10.0)
        vd = model.detection_at(0)

        assert vd is not None
        assert vd.detection.frame_number == sample_detections[0].frame_number

    def test_detection_at_invalid_index(self, qapp, sample_detections):
        """detection_at with an out-of-range index should return None."""
        from seavision.gui.validation.detection_table import (
            DetectionTableModel,
        )

        model = DetectionTableModel()
        model.set_detections(_wrap(sample_detections), fps=10.0)

        vd = model.detection_at(100)  # out of range

        assert vd is None

    def test_frame_numbers_sorted(self, qapp):
        """frame_numbers_sorted should return unique sorted frames."""
        from seavision.gui.validation.detection_table import (
            DetectionTableModel,
        )

        model = DetectionTableModel()
        model.set_detections(_wrap([
            _make_detection(frame=30),
            _make_detection(frame=10),
            _make_detection(frame=30),  # duplicate
            _make_detection(frame=20),
        ]))

        assert model.frame_numbers_sorted() == [10, 20, 30]

