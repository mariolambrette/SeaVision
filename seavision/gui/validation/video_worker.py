"""Background video decoder - runs on a QThread"""

import logging
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from seavision.gui.shared.conversion import numpy_bgr_to_qimage
from seavision.gui.validation.seekable_source import SeekableVideoSource
from seavision.engine.visualiser import FrameAnnotator
from seavision.engine.visualiser.loader import DetectionSource

logger = logging.getLogger(__name__)


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
    video_opened = Signal(object) # VideoMetadata

    # Emitted when an error occurs
    error_occurred = Signal(str) # Error message

    # Emmitted when playback reaches the end of the video
    playback_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Video source
        self._source: SeekableVideoSource | None = None
        
        # Playback state
        self._playing = False

        # Frame annotator instance - stateless, set once for all videos.
        self._annotator = FrameAnnotator()

        # Detection source for annotations (set externally by the main thread)
        self._detection_source: DetectionSource | None = None


    # --- PLAYBACK SLOT & METHODS ---
    @Slot(str, bool)
    def open_video(self, filepath: str, preload: bool = False) -> None:
        """
        Open a video file and emit metadata with the specified loading strategy.
        """
        try:
            self.close_video()
            self._source = SeekableVideoSource(filepath, preload=preload)
            self.video_opened.emit(
                self._source.metadata,
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
        frame = self._annotate_frame(frame, ctx)
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
        frame = self._annotate_frame(frame, ctx)
        image = numpy_bgr_to_qimage(frame)
        self.frame_ready.emit(image, ctx.frame_number, ctx.timestamp)

        # Schedule the next frame
        interval_ms = int(1000 / self._source.metadata.fps)
        QTimer.singleShot(interval_ms, self._playback_tick)

    # --- ANNOTATION SLOTS & METHODS ---
    @Slot(object)
    def set_detection_source(self, source: Optional[DetectionSource]) -> None:
        """
        Set the detection source for overlay rendering.

        Called when a session is opened or when switching videos within a
        session. Pass None to clear detections (e.g. when returning to plain
        video-only mode).
        """
        self._detection_source = source
        logger.debug(
            "Detection source set: %s",
            type(source).__name__ if source else "None"
        )

    def _annotate_frame(self, frame, context):
        """
        Annotate a frame with detection overlaps if a detection source is 
        available. Returns the (possibly annotated) frame.
        """

        if self._detection_source is None:
            return frame
        
        detections = self._detection_source.get_detections_for_frame(
            context.frame_number
        )

        if not detections:
            return frame
        
        return self._annotator.annotate_frame(
            frame, detections, context, copy=True
        )

    # --- CLEANUP ---
    @Slot()
    def close_video(self) -> None:
        """Release the current video."""
        self._playing = False
        if self._source is not None:
            self._source.close()
            self._source = None

    @Slot()
    def clear_detection_source(self) -> None:
        """Remove the detection source (returns to plain video mode)."""    
        self._detection_source = None
