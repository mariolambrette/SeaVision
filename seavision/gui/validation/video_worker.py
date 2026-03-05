"""Background video decoder - runs on a QThread"""

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from seavision.gui.shared.conversion import numpy_bgr_to_qimage
from seavision.gui.validation.seekable_source import SeekableVideoSource


class VideoDecoderWorker(QObject):
    """
    Decodes video frames on a background thread.
    
    All communication is through signals - the main thread never calls methods
    on this object directly. Instead, it emits signals that Qt delivers to this
    worker's slots on the worker thread.
    """

    # Emitted after each frame is decoded and converted
    frame_ready = Signal(object, int, float) # QImage, frame number, timestamp

    # Emited after a video is successfully opened
    video_opened = Signal(object, int) # VideoMetadata max_seek_drift

    # Emitted when an error occurs
    error_occurred = Signal(str) # Error message

    # Emmitted when playback reaches the end of the video
    playback_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._source: SeekableVideoSource | None = None
        self._playing = False

    @Slot(str)
    def open_video(self, filepath: str) -> None:
        """Open a video file and emit metadata."""
        try:
            self.close_video()
            self._source = SeekableVideoSource(filepath)
            self.video_opened.emit(
                self._source.metadata,
                self._source.max_seek_drift
            )

            # Show the first frame immediately
            self.request_frame(0)
        except Exception as e:
            self.error_occurred.emit(str(e))

    @Slot(int)
    def request_frame(self, frame_number: int) -> None:
        """Seek to a frame, decode it, and emit the result."""
        if self._source is None:
            return
        
        self._playing = False # Stop playback if active

        result = self._source.read_at(frame_number)
        if result is None:
            return
        
        frame, ctx = result
        image = numpy_bgr_to_qimage(frame)
        self.frame_ready.emit(image, ctx.frame_number, ctx.timestamp)

    @Slot(int)
    def start_playback(self, from_frame: int) -> None:
        """Begin continuous playback from the given frame."""
        if self._source is None:
            return
        
        self._playing = True
        self._source.seek(from_frame)
        self._playback_tick()

    @Slot()
    def stop_playback(self) -> None:
        """Stop continuous playback."""
        self._playing = False

    def _playback_tick(self) -> None:
        """
        Decode and emit one frame, then schedule the next tick.

        Uses QTimer.singleShot to yield control back to the event loop between
        frames. This allows the worker to process other signals (like
        stop_playback or request_frame) between ticks.
        """
        if not self._playing or self._source is None:
            return
        
        result = self._source.read()
        if result is None:
            self._playing = False
            self.playback_finished.emit()
            return
        
        frame, ctx = result
        image = numpy_bgr_to_qimage(frame)
        self.frame_ready.emit(image, ctx.frame_number, ctx.timestamp)

        # Schedule the next frame
        interval_ms = int(1000 / self._source.metadata.fps)
        QTimer.singleShot(interval_ms, self._playback_tick)

    @Slot()
    def close_video(self) -> None:
        """Release the current video."""
        self._playing = False
        if self._source is not None:
            self._source.close()
            self._source = None
