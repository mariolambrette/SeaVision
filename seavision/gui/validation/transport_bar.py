"""Playback transport controls."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
    seek_requested = Signal(int) # Frame number

    def __init__(self, parent=None):
        """
        Build the layout and connect signals.
        """
        super.__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # --- Buttons ---
        self._prev_btn = QPushButton("⏮")
        self._play_btn = QPushButton("▶/⏸")
        self._next_btn = QPushButton("⏭")

        for btn in (self._prev_btn, self._play_btn, self._next_btn):
            btn.setFixedWidth(50)


        # --- Seek slider ---
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)

        
        # --- Labels ---
        self._frame_label = QLabel("Frame: - / -")
        self._time_label = QLabel("Time: - / -")
        self._frame_label.setFixedWidth(140)
        self._time_label.setFixedWidth(100)

        
        # --- Assemble ---
        layout.addWidget(self._prev_btn)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._next_btn)
        layout.addWidget(self._slider, stretch=1)
        layout.addWidget(self._frame_label)
        layout.addWidget(self._time_label)

        
        # --- Internal wiring ---
        self._prev_btn.clicked.connect(self.prev_frame_clicked)
        self._play_btn.clicked.connect(self.play_pause_clicked)
        self._next_btn.clicked.connect(self.next_frame_clicked)
        self._slider.sliderMoved.connect(self.seek_requested)


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

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS."""
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}:{secs:04.1f}"
