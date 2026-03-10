"""
Validation tab - assembles viewer, transport and worker and creates the tab 
layout.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QMessageBox,
    QSplitter, 
    QVBoxLayout, 
    QWidget,
)

from seavision.gui.shared.session_utils import resolve_video_paths
from seavision.gui.validation.detection_detail import DetectionDetailPanel
from seavision.gui.validation.detection_table import(
    DetectionTableModel,
    DetectionTableView,
)
from seavision.gui.validation.seekable_source import (
    _needs_preload,
    _estimate_memory_mb,
    _available_memory_mb,
    SeekableVideoSource,
)
from seavision.gui.validation.transport_bar import TransportBar
from seavision.gui.validation.video_viewer import FrameDisplay
from seavision.gui.validation.video_worker import VideoDecoderWorker
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
    _request_frame_immediate = Signal(int)
    _set_highlight = Signal(object) # Detection object or None

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Create widgets ---
        self._viewer = FrameDisplay()
        self._transport = TransportBar()
        self._detection_model = DetectionTableModel()
        self._detection_table = DetectionTableView()
        self._detection_table.setModel(self._detection_model)
        self._detail_panel = DetectionDetailPanel()

#        # --- Layout ---
#        layout = QVBoxLayout(self)
#        layout.setContentsMargins(0, 0, 0, 0)
#        layout.addWidget(self._viewer, stretch=1)
#        layout.addWidget(self._transport, stretch=0)

        # --- Layout: three-zone splitter ---
        # Outer splitter: left placeholder | centre viewer | right panel
        self._outer_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left placeholder — becomes VideoListWidget in Phase 5
        self._left_placeholder = QWidget()
        self._left_placeholder.setMinimumWidth(100)
        self._outer_splitter.addWidget(self._left_placeholder)

        # Centre: video viewer
        self._outer_splitter.addWidget(self._viewer)

        # Right: detection table (top) + detail panel (bottom)
        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.addWidget(self._detection_table)
        self._right_splitter.addWidget(self._detail_panel)
        self._right_splitter.setSizes([400, 200])  # 2:1 ratio

        self._outer_splitter.addWidget(self._right_splitter)

        # Set initial sizes: left 150px, centre 700px, right 350px
        self._outer_splitter.setSizes([150, 700, 350])

        # Main layout: splitter on top, transport bar on bottom
        layout = QVBoxLayout(self)
        layout.addWidget(self._outer_splitter, stretch=1)
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
        self._selected_detection_index: int | None = None

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
        self._request_frame_immediate.connect(
            self._worker.request_frame_immediate
        )
        self._set_highlight.connect(self._worker.set_highlight_detection)

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
        self._transport.seek_commited.connect(self._on_seek_committed)
        self._transport.prev_detection_clicked.connect(
            self._on_prev_detection
        )
        self._transport.next_detection_clicked.connect(
            self._on_next_detection
        )

        # --- Connect detection table signals ---
        self._detection_table.detection_selected.connect(
            self._on_detection_selected
        )

        # --- Debounce timer for seek requests ---
        self._seek_timer = QTimer()
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(50)  # ms
        self._seek_timer.timeout.connect(self._do_seek)
        self._pending_seek: int | None = None

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

        # Populate the detection table
        all_detections = []
        for frame_num in filtered_loader.get_frame_numbers_with_detections():
            all_detections.extend(
                filtered_loader.get_detections_for_frame(frame_num)
            )

        self._detection_model.set_detections(all_detections, fps=None)

        # Clear the detail panel and highlight
        self._detail_panel.clear()
        self._selected_detection_index = None
        self._set_highlight.emit(None)

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

        # Clear the detection table and detail panel
        self._detection_model.set_detections([])
        self._detail_panel.clear()
        self._selected_detection_index = None
        self._set_highlight.emit(None)

        preload = self._should_preload(filepath)
        self._request_open.emit(filepath, preload)

    def _on_video_opened(self, metadata: VideoMetadata) -> None:
        """Worker has opened a video — configure the UI."""
        self._metadata = metadata
        self._current_frame = 0
        self._is_playing = False
        self._transport.set_video_info(metadata)

        # Update table with accurate frame rate
        if metadata.fps and metadata.fps > 0:
            self._detection_model._fps = metadata.fps
            self._detection_model.layoutChanged.emit() 

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
    
    def _on_detection_selected(
        self, row: int, frame_number: int,
    ) -> None:
        """
        Handle a detection being selected in the table.

        Seeks the video to the detection's frame, updates the detail panel, and
        requests a frame render with the selected detection highlighted.
        """
        detection = self._detection_model.detection_at(row)
        if detection is None:
            return
        
        self._selected_detection_index = row
        
        # Update the detail panel
        fps = self._metadata.fps
        self._detail_panel.set_detection(detection, fps=fps)

        # If playing, stop before seeking to detection frame.
        if self._is_playing:
            self._on_play_pause()

        # Request the frame with detection highlighting
        self._seek_to_frame_with_highlight(frame_number, row)

    def _seek_to_frame_with_highlight(
            self, frame_number: int, selected_row: int
        ) -> None:
        """Seek to a frame and highlight a specific detection."""
        detection = self._detection_model.detection_at(selected_row)
        self._set_highlight.emit(detection)
        self._request_frame.emit(frame_number)

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

    def _on_next_detection(self) -> None:
        """
        Navigate to the next detection in the table

        Steps through detection sequentially - all detections on the 
        current frame before moving on to the next frame.
        """
        if self._detection_model.detection_count() == 0:
            return
        
        # If nothing is seletected, start with the first detection
        if self._selected_detection_index is None:
            self._detection_table.select_row(0)
            return
        
        next_row = self._selected_detection_index + 1
        if next_row >= self._detection_model.detection_count():
            return # Already at the last detection
        
        self._detection_table.select_row(next_row)

    def _on_prev_detection(self) -> None:
        """
        Navigate to the previous detection in the table.
        """
        if self._detection_model.detection_count() == 0:
            return
        if self._selected_detection_index is None:
            return
        prev_row = self._selected_detection_index - 1
        if prev_row < 0:
            return  # Already at the first detection
        self._detection_table.select_row(prev_row)

    def _on_seek(self, frame_number: int) -> None:
        """User dragged the slider - denouce rapid seeks."""
        if self._is_playing:
            self._request_stop.emit()
            self._is_playing = False
            self._transport.set_playing(False)

        self._pending_seek = frame_number
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _on_seek_committed(self, frame_number: int) -> None:
        """User released the slider - jump directly to the final frame."""
        # Cancel any pending debounced seeks
        self._seek_timer.stop()
        self._pending_seek = None

        if self._is_playing:
            self._request_stop.emit()
            self._is_playing = False
            self._transport.set_playing(False)

        # Set the skip flag directly on the worker — bypasses the signal
        # queue so it takes effect before queued seeks are processed.
        # Safe under Python's GIL for simple attribute assignment.
        self._worker._skip_pending_seeks = True

        # This goes to the end of the queue, but uses the immediate
        # slot which ignores the skip flag and resets it.
        self._request_frame_immediate.emit(frame_number)
    
    def _do_seek(self) -> None:
        """Process the most recent seek request."""
        if self._pending_seek is not None:
            self._request_frame.emit(self._pending_seek)
            self._pending_seek = None

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
