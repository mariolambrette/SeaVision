"""Validation tab - assembles viewer, transport and worker."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from seavision.gui.validation.video_viewer import FrameDisplay
from seavision.gui.validation.video_worker import VideoDecoderWorker
from seavision.gui.validation.transport_bar import TransportBar


class ValidationTab(QWidget):
    """
    Main valdation interface - video viewer with transport controls.
    
    Owns the video decoder worker thread and mediates between the transport bar
    (user input) and the worker (video decoding).
    """

    # Private signals for sending commands to the worker thread. We emit these
    # instead of calling worker methods directly because the worker lives on a
    # different thread.
    _request_open = Signal(str)
    _request_frame = Signal(int)
    _request_play = Signal(int)
    _request_stop = Signal()
    _request_close = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Create widgets ---
        self._viewer = FrameDisplay()
        self._transport = TransportBar()

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._viewer, stretch=1)
        layout.addWidget(self._transport, stretch=0)

        # --- Worker thread ---
        self._thread = QThread()
        self._worker = VideoDecoderWorker()
        self._worker.moveToThread(self._thread)
        self._thread.start()

        # --- State ---
        self._current_frame = 0
        self._is_playing = False
        self._metadata = None

        # --- Connect private signals to worker slots ---
        self._request_open.connect(self._worker.open_video)
        self._request_frame.connect(self._worker.request_frame)
        self._request_play.connect(self._worker.start_playback)
        self._request_stop.connect(self._worker.stop_playback)
        self._request_close.connect(self._worker.close_video)

        # --- Connect worker signals to slots ---
        self._worker.frame_ready.connect(self._viewer.update_frame)
        self._worker.frame_ready.connect(self._on_frame_received)
        self._worker.video_opened.connect(self._on_video_opened)
        self._worker.playback_finished.connect(self._on_playback_finished)
        self._worker.error_occurred.connect(self._on_error)

        # --- Connect transport bar signals ---
        self._transport.play_pause_clicked.connect(self._on_play_pause)
        self._transport.next_frame_clicked.connect(self._on_next_frame)
        self._transport.prev_frame_clicked.connect(self._on_prev_frame)
        self._transport.seek_requested.connect(self._on_seek)

    def open_video(self, filepath: str) -> None:
        """Open a new video (called by Main Window)."""
        self._request_open.emit(filepath)

    def _on_video_opened(self, metadata) -> None:
        """Worker has opened a video - configure the UI."""
        self._metadata = metadata
        self._current_frame = 0
        self._is_playing = False
        self._transport.set_video_info(metadata)

    def _on_frame_received(self, image, frame_number, timestamp) -> None:
        """Worker has decoded a frame — update our bookkeeping."""
        self._current_frame = frame_number
        self._transport.update_position(frame_number, timestamp)

    def _on_play_pause(self) -> None:
        """User clicked play or pause."""
        if self._metadata is None:
            return
        
        if self._is_playing:
            self._request_stop.emit()
            self._is_playing = False
        else:
            self._request_play.emit(self._current_frame)
            self._is_playing = True

        self._transport.set_playing(self._is_playing)

    def _on_next_frame(self) -> None:
        """Step forward one frame."""
        if self._metadata is None:
            return
        
        next_frame = min(self._current_frame + 1, 
                         self._metadata.frame_count - 1)
        self._request_frame.emit(next_frame)

    def _on_prev_frame(self) -> None:
        """Step backward one frame."""
        prev_frame = max(self._current_frame - 1, 0)
        self._request_frame.emit(prev_frame)

    def _on_seek(self, frame_number: int) -> None:
        """User dragged the slider."""
        if self._is_playing:
            self._request_stop.emit()
            self._is_playing = False
            self._transport.set_playing(False)
        self._request_frame.emit(frame_number)

    def _on_playback_finished(self) -> None:
        """Video reached the end."""
        self._is_playing = False
        self._transport.set_playing(False)

    def _on_error(self, message: str) -> None:
        """Worker reported an error."""
        QMessageBox.warning(self, "Video Error", message)

    def shutdown(self) -> None:
        """
        Stop playback, close video and shut down the worker thread.

        Must be called before the application exits, otherwise the background
        thread may hang or print warnings.
        """
        self._request_stop.emit()
        self._request_close.emit()
        self._thread.quit()
        self._thread.wait()
