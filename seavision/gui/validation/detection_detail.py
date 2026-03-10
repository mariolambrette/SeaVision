"""
Detection detail panel - shows properties of the selected detection.
Will eventually be extended to allow editing of bounding box position.
"""

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from seavision.engine.detectors.base import Detection

class DetectionDetailPanel(QWidget):
    """
    Read-only panel displaying all properties of a selected detection.
    
    Uses QFormLayout for a clean label-value grid. Updated whenever the table
    selection changes. Shows placeholder dashes when no detection is selected.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_layout()
        self.clear()

    def _build_layout(self) -> None:
        """Create the label-value pairs."""
        layout = QFormLayout(self)

        self._frame_value = QLabel()
        layout.addRow("Frame:", self._frame_value)

        self._time_value = QLabel()
        layout.addRow("Timestamp:", self._time_value)

        self._confidence_value = QLabel()
        layout.addRow("Confidence:", self._confidence_value)

        self._label_value = QLabel()
        layout.addRow("Label:", self._label_value)

        self._track_value = QLabel()
        layout.addRow("Track ID:", self._track_value)

        self._position_value = QLabel()
        layout.addRow("Centre coordinates (xc, yc):", self._position_value)

        self._bbox_coords_value = QLabel()
        layout.addRow("Bounding box (x1, y1, x2, y2):", self._bbox_coords_value)

        self._size_value = QLabel()
        layout.addRow("Size:", self._size_value)

        self._area_value = QLabel()
        layout.addRow("Area:", self._area_value)

    def set_detection(
        self, detection: Detection, fps: float | None = None
    ) -> None:
        """
        Update all fields to show the given detection's properties.

        Args:
            detection: A detection object from the engine.
            fps: Video frame rate for timestamp calculation.
        """
        self._frame_value.setText(str(detection.frame_number))
        
        if fps is not None and fps > 0:
            timestamp = detection.frame_number / fps
            mins = int(timestamp // 60)
            secs = timestamp % 60
            self._time_value.setText(f"{mins}:{secs:04.1f}")
        else:
            self._time_value.setText("—")

        if detection.confidence is not None:
            self._confidence_value.setText(f"{detection.confidence:.3f}")
        else:
            self._confidence_value.setText("—")

        self._label_value.setText(detection.label if detection.label else "—")

        if detection.track_id is not None:
            self._track_value.setText(str(detection.track_id))
        else:
            self._track_value.setText("—")

        # Position: centre coordinates
        self._position_value.setText(
            f"({detection.xc:.1f}, {detection.yc:.1f})"
        )

        # Bounding box coordinates
        x1 = detection.xc - detection.width / 2
        y1 = detection.yc - detection.height / 2
        x2 = detection.xc + detection.width / 2
        y2 = detection.yc + detection.height / 2
        self._bbox_coords_value.setText(
            f"({x1:.1f}, {y1:.1f}, {x2:.1f}, {y2:.1f})"
        )

        # Size: width x height
        self._size_value.setText(
            f"{detection.width:.1f} x {detection.height:.1f}"
        )

        # Area: width * height
        area = detection.width * detection.height
        self._area_value.setText(f"{area:.0f} px²")

    def clear(self) -> None:
        """Reset all fields to a placeholder state."""
        self._frame_value.setText("—")
        self._time_value.setText("—")
        self._confidence_value.setText("—")
        self._label_value.setText("—")
        self._track_value.setText("—")
        self._position_value.setText("—")
        self._bbox_coords_value.setText("—")
        self._size_value.setText("—")
        self._area_value.setText("—")
