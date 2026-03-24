"""Playback transport controls."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

from seavision.engine.source.base import VideoMetadata


class TransportBar(QWidget):
    """
    Playback controls: prev/next frame, play/pause, seek slider, and
    frame/time display.

    All user actions are exposed as signals - this widget does not know about
    videos or workers.
    """

    play_pause_clicked = Signal()
    next_frame_clicked = Signal()
    prev_frame_clicked = Signal()
    seek_requested = Signal(int) # Frame number, fires during drag
    seek_commited = Signal(int) # Frame number, fires on slider release

    prev_detection_clicked = Signal()
    next_detection_clicked = Signal()

    speed_changed = Signal(float)  # Playback speed multiplier

    def __init__(self, parent=None):
        """
        Build the layout and connect signals.
        """
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # --- Buttons ---
        self._prev_det_btn = QPushButton("⏪")
        self._prev_det_btn.setToolTip("Previous detection (Ctrl+Left)")
        self._prev_det_btn.setFixedWidth(30)

        self._prev_btn = QPushButton("⏮")
        self._prev_btn.setToolTip("Previous frame (Left)")
        self._prev_btn.setFixedWidth(30)

        self._play_btn = QPushButton("▶/⏸")
        self._play_btn.setFixedWidth(60)

        self._next_btn = QPushButton("⏭")
        self._next_btn.setToolTip("Next frame (Right)")
        self._next_btn.setFixedWidth(30)

        self._next_det_btn = QPushButton("⏩")
        self._next_det_btn.setToolTip("Next detection (Ctrl+Right)")
        self._next_det_btn.setFixedWidth(30)

        # --- Seek slider ---
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        
        # --- Labels ---
        self._frame_label = QLabel("Frame: - / -")
        self._time_label = QLabel("Time: - / -")
        self._frame_label.setFixedWidth(140)
        self._time_label.setFixedWidth(100)

        # --- Speed selector ---
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(
            ["0.25x", "0.5x", "1x", "2x", "5x"]
        )
        self._speed_combo.setCurrentIndex(2)  # Default 1x
        self._speed_combo.setFixedWidth(65)
        self._speed_combo.setToolTip("Playback speed")
        self._speed_combo.currentTextChanged.connect(
            self._on_speed_changed
        )

        # --- Assemble ---
        layout.addWidget(self._prev_det_btn)
        layout.addWidget(self._prev_btn)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._next_btn)
        layout.addWidget(self._next_det_btn)
        layout.addWidget(self._slider)
        layout.addWidget(self._frame_label)
        layout.addWidget(self._time_label)
        layout.addWidget(self._speed_combo)
        
        # --- Internal wiring ---
        self._prev_det_btn.clicked.connect(self.prev_detection_clicked)
        self._prev_btn.clicked.connect(self.prev_frame_clicked)
        self._play_btn.clicked.connect(self.play_pause_clicked)
        self._next_btn.clicked.connect(self.next_frame_clicked)
        self._next_det_btn.clicked.connect(self.next_detection_clicked)
        self._slider.sliderMoved.connect(self.seek_requested)
        self._slider.sliderReleased.connect(
            self._on_slider_released
        )

        # Disable until a video is loaded
        self.setEnabled(False)

        # Store total frame count for labels
        self._total_frames = 0
        self._total_duration = 0.0

    def set_video_info(self, metadata: VideoMetadata) -> None:
        """Configure controls for a newly opened video."""
        self._total_frames = metadata.frame_count
        self._total_duration = metadata.duration
        self._slider.setRange(0, max(0, metadata.frame_count - 1))
        self.update_position(0, 0.0)
        self.setEnabled(True)

    def update_position(self, frame_number: int, timestamp: float) -> None:
        """Update the display to reflect the current playback position."""
        # Block signals to prevent the programmatic setValue from triggering
        # sliderMoved -> seek_requested -> infinite loop
        self._slider.blockSignals(True)
        self._slider.setValue(frame_number)
        self._slider.blockSignals(False)

        self._frame_label.setText(
            f"Frame: {frame_number} / {self._total_frames}"
        )
        self._time_label.setText(
            f"{self._format_time(timestamp)} / "
            f"{self._format_time(self._total_duration)}"
        )

    def set_playing(self, is_playing: bool) -> None:
        """Update the play/pause button text."""
        self._play_btn.setText("⏸" if is_playing else "▶")

    def _on_slider_released(self) -> None:
        """Slider was released - emit the final position."""
        self.seek_commited.emit(self._slider.value())

    def _on_speed_changed(self, text: str) -> None:
        """Parse the speed text and emit the multiplier."""
        try:
            multiplier = float(text.rstrip("x"))
            self.speed_changed.emit(multiplier)
        except ValueError:
            pass

    def set_detection_nav_enabled(self, enabled: bool) -> None:
        """Enable or disable the detection navigation buttons."""
        self._prev_det_btn.setEnabled(enabled)
        self._next_det_btn.setEnabled(enabled)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS."""
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}:{secs:04.1f}"
