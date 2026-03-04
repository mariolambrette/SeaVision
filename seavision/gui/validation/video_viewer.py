"""Video frame display widget."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

class FrameDisplay(QLabel):
    """
    Displays video frames sclaed to fit the available space.

    Recieves QImage objects (from the video worker), converts them to QPixmap,
    and renders them centered with correct aspect ratio. Handles window resizing
    by re-scaling the last displayed frame.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set alignment policies
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, 
            QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(320, 240)

        # Placeholder appearance
        self.setStyleSheet("background-color: #1e1e1e; color: #888888;")
        self.setText("No video loaded")

        # Placeholder for the unscaled original frame
        self._original_pixmap: QPixmap | None = None

    def update_frame(self, image: QImage, frame_number: int,
                     timestamp: float) -> None:
        """
        Display a new frame from the video worker.

        Args:
            image: The frame as a QImage.
            frame_number: Frame index (not used here, but part of the signal
                signature - other slots use it).
            timestamp: Time in seconds (same)
        """
        self._original_pixmap = QPixmap.fromImage(image)
        self._scale_and_display()
        
    def _scale_and_display(self) -> None:
        """Scale the stored pixmap to fit the current widget size."""
        if self._original_pixmap is None:
            return
        
        scaled = self._original_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        """Re-scale the frame when the widget is resized."""
        self._scale_and_display()
        super().resizeEvent(event)
    