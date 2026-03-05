"""Validation tab - assembles viewer, transport and worker."""

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from seavision.gui.validation.video_viewer import FrameDisplay
from seavision.gui.validation.video_worker import VideoDecoderWorker
from seavision.gui.validation.transport_bar import TransportBar
from seavision.gui.shared.session_utils import resolve_video_paths
from seavision.gui.validation.seekable_source import (
    _needs_preload,
    _estimate_memory_mb,
    _available_memory_mb,
    SeekableVideoSource
)
from seavision.engine.visualiser import CSVDetectionLoader
from seavision.engine.source.base import VideoMetadata

logger = logging.getLogger(__name__)


class ValidationTab(QWidget):
    """
    Main validation interface - video viewer with transport controls.
    
    Owns the video decoder worker thread and mediates between the transport bar
    (user input) and the worker (video decoding).
    """

    # Private signals for sending commands to the worker thread. We emit these
    # instead of calling worker methods directly because the worker lives on a
    # different thread.
    _request_open = Signal(str, bool) # filepath, preload
    _request_frame = Signal(int)
    _request_play = Signal(int)
    _request_stop = Signal()
    _request_close = Signal()
    _set_detection_source = Signal(object)
    _clear_detection_source = Signal()

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
        # Playback state
        self._current_frame = 0
        self._is_playing = False
        self._metadata = None

        # Session state
        self._csv_loader: CSVDetectionLoader | None = None
        self._video_paths: dict[str, str] = {}
        self._active_source: str | None = None

        # --- Connect private signals to worker slots ---
        self._request_open.connect(self._worker.open_video)
        self._request_frame.connect(self._worker.request_frame)
        self._request_play.connect(self._worker.start_playback)
        self._request_stop.connect(self._worker.stop_playback)
        self._request_close.connect(self._worker.close_video)
        self._set_detection_source.connect(self._worker.set_detection_source)
        self._clear_detection_source.connect(
            self._worker.clear_detection_source
        )

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

    def open_session(
            self, csv_path: str, video_dir: str
    ) -> None:
        """
        Open a detection session from a CSV file and video directory.

        Parses the CSV, resolves source videos against the directory,
        and opens the first resolved video with detection overlays.

        Args:
            csv_path: Path to the detection CSV file.
            video_dir: Directory containing the source video files.
        """
        # --- Parse the CSV ---
        try:
            loader = CSVDetectionLoader(csv_path)
        except (FileNotFoundError, ValueError) as e:
            QMessageBox.warning(
                self,
                "CSV Error",
                f"Failed to load detection CSV:\n\n{e}",
            )
            return
        
        # --- Resolve video files ---
        resolved, s3_sources = resolve_video_paths(
            loader.sources_in_file,
            video_dir
        )

        # --- Report S3 sources ---
        if s3_sources:
            QMessageBox.warning(
                self,
                "S3 Videos Not Supported",
                f"This CSV references {len(s3_sources)} S3 video(s).\n\n"
                f"S3 download is not yet implemented. Please download "
                f"the videos manually to a local directory and try again.\n\n"
                f"S3 sources:\n"
                + "\n".join(f"  • {s}" for s in s3_sources[:5])
                + ("\n  ..." if len(s3_sources) > 5 else ""),
            )

        # --- Check we found at least one video ---
        if not resolved:
            expected = [Path(s).name for s in loader.sources_in_file
                        if not s.startswith("s3://")]
            QMessageBox.warning(
                self,
                "No Videos Found",
                f"No matching video files found in:\n"
                f"  {video_dir}\n\n"
                f"Expected filenames:\n"
                + "\n".join(f"  • {name}" for name in expected[:10])
                + ("\n  ..." if len(expected) > 10 else ""),
            )
            return
        
        # --- Store session state ---
        self._csv_loader = loader
        self._video_paths = resolved

        # --- Open the first video ---
        first_source = next(
            s for s in loader.sources_in_file if s in resolved
        )
        self._open_video_for_source(first_source)

        logger.info(
            "Session opened: %s — %d sources, %d resolved",
            csv_path,
            len(loader.sources_in_file),
            len(resolved),
        )

    def _open_video_for_source(self, source_name: str) -> None:
        """
        Open a specific source video with its detection overlay.

        Creates a filtered CSVDetectionLoader for just this video's detections
        and sends it to the worker alongside the video path.

        Args:
            source_name: The source_file value from the CSV.
        """
        local_path = self._video_paths.get(source_name)
        if local_path is None:
            logger.error(
                "No local path for source: %s", 
                source_name
            )
            return

        self._active_source = source_name

        # Create a filtered loader for just this video's detections
        filtered_loader = CSVDetectionLoader(
            str(self._csv_loader.csv_path),
            source_file=source_name,
        )

        # Send the detection source
        self._set_detection_source.emit(filtered_loader)

        # Check for preload
        preload = self._should_preload(local_path)

        # Load video with the specified strategy
        self._request_open.emit(local_path, preload)

        logger.info(
            "Opened source '%s' (%s) — %d detection frames",
            source_name,
            local_path,
            len(filtered_loader.get_frame_numbers_with_detections()),
        )
    
    def open_video(self, filepath: str) -> None:
        """Open a video file without detections (called by Main Window)."""
        # Clear any active session state
        self._csv_loader = None
        self._video_paths = {}
        self._active_source = None
        self._clear_detection_source.emit()

        preload = self._should_preload(filepath)
        self._request_open.emit(filepath, preload)

    def _on_video_opened(self, metadata) -> None:
        """Worker has opened a video — configure the UI."""
        self._metadata = metadata
        self._current_frame = 0
        self._is_playing = False
        self._transport.set_video_info(metadata)

    # --- Video preload methods ---
    def _confirm_preload(self, filepath: str, metadata: VideoMetadata) -> bool:
        """
        Ask the user whether to pre-load a video that requires it for accurate
        seeking. Returns True for pre-load, False for fallback.
        """
        estimated_mb = _estimate_memory_mb(
            metadata.width, metadata.height, metadata.frame_count
        )
        available_mb = _available_memory_mb()

        if available_mb is not None:
            memory_line = (
                f"Estimated memory usage: {estimated_mb:.1f} MB\n"
                f"Available RAM: {available_mb:.1f} MB"
            )
        else:
            memory_line = (
                f"Estimated memory usage: {estimated_mb:.1f} MB\n"
                f"Available RAM: NA"
            )
        
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Video Format Notice")
        msg.setText(
            f"This video format ({Path(filepath).suffix}) does not support "
            f"frame-accurate seeking.\n\n"
            f"For accurate detection overlay alignment, the full video can be "
            f"loaded into memory. This is recomended for validation work.\n\n"
            f"{memory_line}\n"
            f"Alternatively, you can use standard seeking, but detection "
            f"overlays may not align accurately with the video frames."
        )

        preload_btn = msg.addButton(
            "Load into Memory (Recomended)", QMessageBox.ButtonRole.AcceptRole
        )
        _fallback_btn = msg.addButton(
            "Use Standard Seeking", QMessageBox.ButtonRole.RejectRole
        )
        msg.setDefaultButton(preload_btn)

        msg.exec()
        return msg.clickedButton() == preload_btn

    def _should_preload(self, filepath: str) -> bool:
        """Determine whether to pre-load based on format and user choice."""
        if not _needs_preload(filepath):
            return False

        # Read metadata to calculate memory
        metadata = SeekableVideoSource._read_metadata(filepath)
        return self._confirm_preload(filepath, metadata)

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
        self._clear_detection_source.emit()
        self._request_close.emit()
        self._thread.quit()
        self._thread.wait()
