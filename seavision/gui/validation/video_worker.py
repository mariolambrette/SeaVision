"""Background video decoder - runs on a QThread"""

import logging
import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from seavision.gui.shared.conversion import numpy_bgr_to_qimage
from seavision.gui.validation.seekable_source import SeekableVideoSource
from seavision.engine.detectors import Detection
from seavision.engine.source import FrameContext
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

        # Flag to skip pending seek requests
        self._skip_pending_seeks = False

        # Selected detection for highlighting (set externally by the
        # main thread)
        self._highlight_detection: Detection | None = None


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
        if self._skip_pending_seeks:
            return # return immediately to skip pending seeks.
        
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
    def request_frame_immediate(self, frame_number: int) -> None:
        """
        Seek to a frame unconditionally - never skipped.
        
        Clears the skip flag so that future preview seeks (from the next drag)
        will be processed normally.
        """
        self._skip_pending_seeks = False
        self._playing = False

        if self._source is None:
            return

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

        tick_start = time.perf_counter()

        result = self._source.read()
        if result is None:
            self._playing = False
            self.playback_finished.emit()
            return
        
        frame, ctx = result
        frame = self._annotate_frame(frame, ctx)
        image = numpy_bgr_to_qimage(frame)
        self.frame_ready.emit(image, ctx.frame_number, ctx.timestamp)

        # Subtract the time already spent from the target interval
        elapsed_ms = (time.perf_counter() - tick_start) * 1000
        target_ms = 1000 / self._source.metadata.fps
        remaining_ms = max(1, int(target_ms - elapsed_ms))

        QTimer.singleShot(remaining_ms, self._playback_tick)

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

    @Slot(object)
    def set_highlight_detection(self, detection: Detection | None) -> None:
        """
        Set which detection to highlight with a distinct colour.

        Args:
            detection: The detection object to highlight, or None to clear the 
                highlight.
        """
        self._highlight_detection = detection

    def _annotate_frame(self, frame, context: FrameContext):
        """
        Annotate a frame with detection overlays and optional highlight.

        The standard FrameAnnotator draws all detections. If a highlight
        detection is set, we draw an additional rectangle on the selected
        detection with a distinct colour and thicker line.
        """

        if self._detection_source is None:
            return frame
        
        detections = self._detection_source.get_detections_for_frame(
            context.frame_number
        )

        if not detections:
            return frame
        
        # Initially, annotate all detections normally
        frame = self._annotator.annotate_frame(
            frame, detections, context, copy=True
        )
    
        # Highlight the selected detection if it's on this frame
        if self._highlight_detection is not None:
            hl = self._highlight_detection
            if hl.frame_number == context.frame_number:
                # Match by coordinates
                for det in detections:
                    if (det.xc == hl.xc and det.yc == hl.yc
                            and det.width == hl.width
                            and det.height == hl.height):
                        self._draw_highlight(frame, det)
                        break

        return frame
    
    @staticmethod
    def _draw_highlight(frame, detection: Detection):
        """
        Draw a highlight rectangle on the selected detection.
        
        Uses cyan (BGR: 255, 255, 0) with a thicker line to
        distinguish it from the standard annotation boxes.
        """
        import cv2

        # Convert from centre format to corner format
        x1 = int(detection.xc - detection.width / 2)
        y1 = int(detection.yc - detection.height / 2)
        x2 = int(detection.xc + detection.width / 2)
        y2 = int(detection.yc + detection.height / 2)

        # Cyan highlight, 3px thick (standard boxes are 1px)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 3)

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
