"""Video frame display widget."""

from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtGui import QCursor, QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

class FrameDisplay(QLabel):
    """
    Displays video frames sclaed to fit the available space.

    Recieves QImage objects (from the video worker), converts them to QPixmap,
    and renders them centered with correct aspect ratio. Handles window resizing
    by re-scaling the last displayed frame.
    """

    # Emitted when the user clicks the frame in 'add' mode.
    frame_clicked = Signal(float, float)  # x, y in frame's pixel space

    def __init__(self, parent=None):
        super().__init__(parent)

        # Detection adding
        self._add_mode = False
        self._frame_width: int = 0
        self._frame_height: int = 0

        # Set alignment policies
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, 
            QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(320, 240)

        # Placeholder appearance
        self.setStyleSheet("background-color: #1e1e1e; color: #888888;")
        self.setText(
            "Open a video or session to begin\n\n"
            "File → New Session (Ctrl+N)\n"
            "File → Open Video (Ctrl+O)\n\n"
            "Or drag a CSV, video or .seavision-session file here"
        )

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
        # Store frame dimensions
        self._frame_width = image.width()
        self._frame_height = image.height()
        
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

    
    # --- Handle adding detection ---
    def _widget_to_frame_coords(
        self, widget_x: int, widget_y: int
    ) -> tuple[float, float] | None:
        """
        Convert widget pixel coordinates to original frame coordinates.

        The label displays the frame scaled to fit with aspect ratio preserved.
        This method reverses that transformation.

        Returns:
            (frame_x, frame_y) in the original frame's pixel space, or None if
            the click is outside the displayed frame area (i.e. on the
            letterbox area).
        """
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return None
        
        if self._frame_width == 0 or self._frame_height == 0:
            return None
        
        # The displayed pixmap size (after scaling to fit the label)
        display_w = pixmap.width()
        display_h = pixmap.height()

        # Calculate the label ofest
        offset_x = (self.width() - display_w) / 2
        offset_y = (self.height() - display_h) / 2

        # Position relative to the displayed image
        rel_x = widget_x - offset_x
        rel_y = widget_y - offset_y

        # Check bounds to see if click is in letterbox area
        if rel_x < 0 or rel_y < 0:
            return None
        if rel_x > display_w or rel_y > display_h:
            return None
        
        # Scale back to original frame coordinates
        frame_x = rel_x * (self._frame_width / display_w)
        frame_y = rel_y * (self._frame_height / display_h)

        return frame_x, frame_y
    
    def set_add_mode(self, enabled: bool) -> None:
        """Toggle add-detection mode. Changes the cursor as a visual cue."""
        self._add_mode = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        """Handle clicks - in add mode, emit the frame coordinates."""
        if self._add_mode and event.button() == Qt.MouseButton.LeftButton:
            coords = self._widget_to_frame_coords(
                event.position().x(), event.position().y()
            )
            if coords is not None:
                frame_x, frame_y = coords
                self.frame_clicked.emit(frame_x, frame_y)
            # Exit add mode after one click
            self.set_add_mode(False)
        else:
            super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:
        """Re-scale the frame when the widget is resized."""
        self._scale_and_display()
        super().resizeEvent(event)
    