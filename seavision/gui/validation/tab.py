"""
Validation tab - assembles viewer, transport and worker and creates the tab 
layout.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter, 
    QVBoxLayout, 
    QWidget,
)
from PySide6.QtGui import(
    QKeySequence,
    QShortcut,
)

from seavision.gui.shared.session_utils import resolve_video_paths
from seavision.gui.validation.detection_detail import DetectionDetailPanel
from seavision.gui.validation.detection_table import(
    DetectionFilterProxy,
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
from seavision.gui.validation.validation_model import (
    ValidationModel,
    ValidationStatus,
    ValidatedDetection,
)
from seavision.gui.validation.video_viewer import FrameDisplay
from seavision.gui.validation.video_worker import VideoDecoderWorker
from seavision.engine.visualiser import (
    CSVDetectionLoader,
    ListDetectionSource,
)
from seavision.engine.source.base import VideoMetadata

logger = logging.getLogger(__name__)


_STATUS_FILTER_MAP = {
    "Show: All": None,
    "Show: Pending": ValidationStatus.PENDING,
    "Show: Confirmed": ValidationStatus.CONFIRMED,
    "Show: Rejected": ValidationStatus.REJECTED,
    "Show: Skipped": ValidationStatus.SKIPPED,
    "Show: Corrected": ValidationStatus.CORRECTED,
}


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

        # === Action buttons ---
        button_container = QVBoxLayout()

        # Top row - review actions
        review_row = QHBoxLayout()
        self._confirm_btn = QPushButton("Confirm (C)")
        self._confirm_btn.setStyleSheet(
            "QPushButton { background-color: #2d5a3d; color: white; "
            "padding: 8px 16px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #555; color: #999; }"
        )
        self._confirm_btn.setToolTip(
            "Confirm selected detection (C)\n"
            "Shift+C to confirm all on this frame"
        )

        self._reject_btn = QPushButton("Reject (R)")
        self._reject_btn.setStyleSheet(
            "QPushButton { background-color: #8b2020; color: white; "
            "padding: 8px 16px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #555; color: #999; }"
        )
        self._reject_btn.setToolTip(
            "Reject selected detection (R)\n"
            "Shift+R to reject all on this frame"
        )

        self._skip_btn = QPushButton("Skip (S)")
        self._skip_btn.setStyleSheet(
            "QPushButton { background-color: #555; color: white; "
            "padding: 8px 16px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #444; color: #777; }"
        )
        self._skip_btn.setToolTip(
            "Skip selected detection (S)\n"
            "Shift+S to skip all on this frame"
        )

        review_row.addWidget(self._confirm_btn)
        review_row.addWidget(self._reject_btn)
        review_row.addWidget(self._skip_btn)

        # Bottom row - manual add/remove
        edit_row = QHBoxLayout()

        self._add_btn = QPushButton("Add Detection (A)")
        self._add_btn.setStyleSheet(
            "QPushButton { background-color: #2d6da8; color: white; "
            "padding: 8px 16px; }"
            "QPushButton:disabled { background-color: #444; color: #777; }"
            "QPushButton:checked { background-color: #1a4a7a; "
            "border: 2px solid #88bbee; }"
        )
        self._add_btn.setCheckable(True)
        self._add_btn.setToolTip(
            "Toggle 'add detection' mode. When enabled, click on frame to add a detection."
        )
        self._add_btn.toggled.connect(self._on_add_mode_toggled)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setStyleSheet(
            "QPushButton { background-color: #6b3a3a; color: white; "
            "padding: 8px 16px; }"
            "QPushButton:disabled { background-color: #444; color: #777; }"
        )
        self._remove_btn.setToolTip(
            "Remove a manually added detection (not available for "
            "pipeline detections)"
        )

        edit_row.addWidget(self._add_btn)
        edit_row.addWidget(self._remove_btn)

        # Layout in container
        button_container.addLayout(review_row)
        button_container.addLayout(edit_row)

        self._confirm_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._remove_btn.setEnabled(False)
        self._add_btn.setEnabled(False)

        # --- Layout: three-zone splitter ---
        # Outer splitter: left placeholder | centre viewer | right panel
        self._outer_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left placeholder — becomes VideoListWidget in Phase 5
        self._left_placeholder = QWidget()
        self._left_placeholder.setMinimumWidth(100)
        self._outer_splitter.addWidget(self._left_placeholder)

        # Centre: video viewer
        self._outer_splitter.addWidget(self._viewer)

        # --- Table + filter controls ---
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        # Add filtering row to layout
        filter_row = QHBoxLayout()

        # Status filter
        self._status_filter_combo = QComboBox()
        self._status_filter_combo.addItems([
            "Show: All",
            "Show: Pending",
            "Show: Confirmed",
            "Show: Rejected",
            "Show: Skipped",
            "Show: Corrected",
            "Show: Manual",
        ])
        self._status_filter_combo.currentTextChanged.connect(
            self._on_status_filter_changed
        )

        # Class filter
        self._class_filter_combo = QComboBox()
        self._class_filter_combo.addItem("Class: All")
        # Populated dynamically when session opens
        self._class_filter_combo.currentTextChanged.connect(
            self._on_class_filter_changed
        )

        filter_row.addWidget(self._status_filter_combo)
        filter_row.addWidget(self._class_filter_combo)

        table_layout.addLayout(filter_row)
        table_layout.addWidget(self._detection_table, stretch = 1)

        # Build detection detail widget
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        detail_layout.addWidget(self._detail_panel, stretch=1)
        detail_layout.addLayout(button_container)
        
        # Right: detection table (top) + detail panel (bottom)
        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.addWidget(table_container)
        self._right_splitter.addWidget(detail_container)
        self._right_splitter.setSizes([400, 220])

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
        self._active_source_file: str | None = None
        self._validation_model: ValidationModel | None = None
        self._selected_detection: ValidatedDetection | None = None

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

        # --- Connect action button clicks ---
        self._confirm_btn.clicked.connect(self._on_confirm)
        self._reject_btn.clicked.connect(self._on_reject)
        self._skip_btn.clicked.connect(self._on_skip)
        self._remove_btn.clicked.connect(self._on_remove)

        # --- Connect detection addition signals ---
        self._viewer.frame_clicked.connect(
            self._on_frame_clicked_for_add
        )

        # --- Debounce timer for seek requests ---
        self._seek_timer = QTimer()
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(50)  # ms
        self._seek_timer.timeout.connect(self._do_seek)
        self._pending_seek: int | None = None

        # --- Focus ---
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # --- Keyboard shortcuts ---
        self._setup_shortcuts()

    
    def _show_status(self, message: str) -> None:
        """Show a message in the main window's status bar."""
        main_window = self.window()
        if isinstance(main_window, QMainWindow):
            main_window.statusBar().showMessage(message)
        
    def _clear_status(self) -> None:
        """Clear the status bar message."""
        main_window = self.window()
        if isinstance(main_window, QMainWindow):
            main_window.statusBar().clearMessage()
    
    def _setup_shortcuts(self) -> None:
        """Register keyboard shortcuts for the review workflow."""

        # Store shortcut references
        self._shortcuts = []

        def _add(key: str, slot) -> None:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

        _add("C", self._on_confirm)
        _add("Shift+C", self._on_confirm_all_on_frame)
        _add("1", self._on_confirm)
        _add("R", self._on_reject)
        _add("Shift+R", self._on_reject_all_on_frame)
        _add("2", self._on_reject)
        _add("S", self._on_skip)
        _add("Shift+S", self._on_skip_all_on_frame)
        _add("3", self._on_skip)
        _add("N", self._advance_to_next)
        _add("A", self._toggle_add_mode)
        _add("Space", self._on_play_pause)
        _add("Left", self._on_prev_frame)
        _add("Right", self._on_next_frame)
        _add("Ctrl+Left", self._on_prev_detection)
        _add("Ctrl+Right", self._on_next_detection)

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

        # --- Create validation model ---
        self._validation_model = ValidationModel(loader, parent=self)

        # --- Populate the class filter from validation model's labels ---
        self._populate_class_filter()

        # --- Wire validation model signals ---
        self._validation_model.detection_status_changed.connect(
            self._on_detection_status_changed
        )
        self._validation_model.progress_changed.connect(
            self._on_progress_changed
        )
        self._validation_model.detection_added.connect(
            self._on_detection_added
        )
        self._validation_model.detection_removed.connect(
            self._on_detection_removed
        )

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

        Queries the ValidationModel for this video's detections and populates
        the table with ValidatedDetection objects.

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

        self._active_source_file = source_name

        # --- Send the detection source to the worker ---
        # The worker needs a CSVDetectionLoader for the annotator. Create a
        # filtered one for just this video's detections
        filtered_loader = CSVDetectionLoader(
          str(self._csv_loader.csv_path),
          source_file=source_name,
        )
        self._set_detection_source.emit(filtered_loader)

        # --- Populate the detection table from the ValidationModel ---
        validated_dets = self._validation_model.get_detections_for_video(
            source_name
        ) 
        fps = self._metadata.fps if self._metadata else None
        self._detection_model.set_detections(validated_dets, fps=fps)

        # --- Clear selection state ---
        self._detail_panel.clear()
        self._selected_detection = None
        self._set_highlight.emit(None)

        # --- Open video
        preload = self._should_preload(local_path)
        self._request_open.emit(local_path, preload)

        logger.info(
            "Opened source '%s' (%s) — %d detection frames",
            source_name,
            local_path,
            len(filtered_loader.get_frame_numbers_with_detections()),
        )

    def _refresh_worker_detection_source(self) -> None:
        """
        Rebuild the worker's detection source from the ValidationModel.

        Called after any change that affects which detections exist (manual add/
        remove). This ensures the frameAnnotator sees manual detections
        alongside pipeline detections.
        """
        if self._validation_model is None:
            return
        if self._active_source_file is None:
            return
        
        # Get all detections for the current video (inclusing manual)
        all_vds = self._validation_model.get_detections_for_video(
            self._active_source_file
        )

        # Extract the raw Detection objects for the annotator
        raw_detections = [vd.detection for vd in all_vds]

        # Build a new detection source and send it to the worker
        source = ListDetectionSource(
            raw_detections, self._active_source_file
        )
        self._set_detection_source.emit(source)
    
    def open_video(self, filepath: str) -> None:
        """Open a video file without detections (called by Main Window)."""
        # Clear any active session state
        self._csv_loader = None
        self._video_paths = {}
        self._active_source_file = None
        self._validation_model = None
        self._clear_detection_source.emit()

        # Clear the detection table and detail panel
        self._detection_model.set_detections([])
        self._detail_panel.clear()
        self._selected_detection = None
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
        vd = self._detection_model.detection_at(row)
        if vd is None:
            return

        self._selected_detection = vd

        # Update detection detail panel
        fps = self._metadata.fps if self._metadata else None
        self._detail_panel.set_detection(vd, fps=fps)

        # Enable action buttons
        self._confirm_btn.setEnabled(True)
        self._reject_btn.setEnabled(True)
        self._skip_btn.setEnabled(True)
        self._remove_btn.setEnabled(
            vd.is_manual if vd else False
        )

        if self._is_playing:
            self._on_play_pause()

        self._seek_to_frame_with_highlight(frame_number, vd)

    def _seek_to_frame_with_highlight(
            self, frame_number: int, vd: ValidatedDetection | None
        ) -> None:
        """Seek to a frame and highlight a specific detection."""
        if vd is None:
            self._set_highlight.emit(None)
        else:
            self._set_highlight.emit(vd.detection)
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
        if self._selected_detection is None:
            self._detection_table.select_row(0)
            return
        
        # Find the current row by matching the selected detection's ID
        current_row = self._find_row_for_detection(self._selected_detection)
        if current_row is None:
            self._detection_table.select_row(0)
            return
        
        next_row = current_row + 1
        if next_row >= self._detection_model.detection_count():
            return
        
        self._detection_table.select_row(next_row)

    def _on_prev_detection(self) -> None:
        """
        Navigate to the previous detection in the table.
        """
        if self._detection_model.detection_count() == 0:
            return
        if self._selected_detection is None:
            return

        current_row = self._find_row_for_detection(self._selected_detection)
        if current_row is None:
            return
        
        prev_row = current_row - 1
        if prev_row < 0:
            return
        
        self._detection_table.select_row(prev_row)

    def _find_row_for_detection(
        self, vd: ValidatedDetection
    ) -> int | None:
        """Find the source-model row index for a ValidatedDetection."""
        for row in range(self._detection_model.detection_count()):
            candidate = self._detection_model.detection_at(row)
            if candidate is not None and candidate.id == vd.id:
                return row
        
        return None

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

    # --- Deteection status ---
    def _on_detection_status_changed(
        self, detection_id: int, new_status: ValidationStatus
    ) -> None:
        """
        Handle a detection's dtatus changing.

        Finds the row in the table model and emits dataChanged so the view
        repaints that row with updated status and colours.
        """
        # Find which row this detection is in the source model
        for row, vd in enumerate(self._detection_model._detections):
            if vd.id == detection_id:
                # Emit dataChanged so the entire row
                top_left = self._detection_model.index(row, 0)
                bottom_right = self._detection_model.index(
                    row, self._detection_model.columnCount() - 1
                )
                self._detection_model.dataChanged.emit(
                    top_left, bottom_right
                )
                break

    def _on_progress_changed(self, progress: dict) -> None:
        """Update the status bar with progress."""
        if self._active_source_file is None:
            return
        
        filename = Path(self._active_source_file).name
        total = progress["total"]
        reviewed = progress["reviewed"]
        confirmed = progress["confirmed"]
        rejected = progress["rejected"]
        skipped = progress["skipped"]
        manual = progress["manual"]

        message = (
            f"{filename} — {reviewed}/{total} reviewed — "
            f"{confirmed} confirmed, {rejected} rejected, "
            f"{skipped} skipped"

        )
        if manual > 0:
            message += f", {manual} manually added"

        self._show_status(message)

    def _on_detection_added(self, vd: ValidatedDetection) -> None:
        """Handle a manual detection being added."""
        if vd.detection.source_file == self._active_source_file:
            self._detection_model.append_detection(vd)
            self._select_validated_detection(vd)
            self._refresh_worker_detection_source()
            self._request_frame.emit(self._current_frame)

    def _on_detection_removed(self, detection_id: int) -> None:
        """Handle a manual detection being removed (implemented in Step 7)."""
        self._detection_model.remove_detection_by_id(detection_id)
        self._selected_detection = None
        self._confirm_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._remove_btn.setEnabled(False)
        self._refresh_worker_detection_source()
        self._request_frame.emit(self._current_frame)

    # --- Action button handlers ---
    def _on_confirm(self) -> None:
        """Mark the selected detection as confirmed."""
        self._apply_status(ValidationStatus.CONFIRMED)

    def _on_reject(self) -> None:
        """Mark the selected detection as rejected."""
        self._apply_status(ValidationStatus.REJECTED)

    def _on_skip(self) -> None:
        """Mark the selected detection as skipped."""
        self._apply_status(ValidationStatus.SKIPPED)

    def _on_remove(self) -> None:
        """Remove the selected manual detection."""
        if self._validation_model is None:
            return
        
        if self._selected_detection is None:
            return

        self._validation_model.remove_detection(
            self._selected_detection.id
        )

    def _on_confirm_all_on_frame(self) -> None:
        """Confirm all detections on the current frame."""
        self._apply_status_to_frame(ValidationStatus.CONFIRMED)

    def _on_reject_all_on_frame(self) -> None:
        """Reject all detections on the current frame."""
        self._apply_status_to_frame(ValidationStatus.REJECTED)

    def _on_skip_all_on_frame(self) -> None:
        """Skip all detections on the current frame."""
        self._apply_status_to_frame(ValidationStatus.SKIPPED)

    def _apply_status_to_frame(self, status: ValidationStatus) -> None:
        """
        Apply a review status to all unreviewed detections on the current frame.

        Iterates all detections for the current video and frame number, skipping
        any that alreayd have a non-PENDING status. After updating all of them,
        advances to the next PENDING detection.
        """
        if self._validation_model is None:
            return
        if self._active_source_file is None:
            return
        
        frame_dets = self._validation_model.get_detections_for_frame(
            self._active_source_file, self._current_frame
        )

        if not frame_dets:
            return
        
        changed = 0
        for vd in frame_dets:
            if vd.status == ValidationStatus.PENDING and vd.status != status:
                self._validation_model.set_status(vd.id, status)
                changed += 1

        if changed > 0:
            status_name = status.name.lower()
            self._show_status(
                f"{changed} detection{'s' if changed != 1 else ''} "
                f"{status_name} on frame {self._current_frame}"
            )

        self._advance_to_next()

    def _apply_status(self, status: ValidationStatus) -> None:
        """
        Apply a review status to the currently selected detection, then advance
        to the next unreviewed detection.
        """
        if self._validation_model is None:
            return
        
        if self._selected_detection is None:
            return

        if self._selected_detection.status == status:
            return

        self._validation_model.set_status(
            self._selected_detection.id, status
        )
        self._advance_to_next()

    def _advance_to_next(self) -> None:
        """Advance to the next unreviewed detection in the current video."""
        if self._validation_model is None:
            return
        if self._active_source_file is None:
            return
        
        current_id = (
            self._selected_detection.id
            if self._selected_detection is not None
            else -1
        )

        next_det = self._validation_model.get_next_unreviewed(
            self._active_source_file, after_id=current_id
        )

        if next_det is not None:
            self._select_validated_detection(next_det)
        else:
            self._show_status(
                "All detections reviewed for this video."
            )

    def _select_validated_detection(
            self, validated_det: ValidatedDetection
        ) -> None:
        """
        Select a ValidatedDetection in the table, which triggers click-to-seek
        via the existing selection change handler.
        """
        # Find the source model row
        for row, vd in enumerate(self._detection_model._detections):
            if vd.id == validated_det.id:
                self._detection_table.select_row(row)
                return


    # --- Table filtering helpers ---
    def _on_status_filter_changed(self, text: str) -> None:
        """Update the table filter when the status combo changes."""
        proxy = self._detection_table.model()
        if not isinstance(proxy, DetectionFilterProxy):
            raise(RuntimeError("Expected detection table model to be a DetectionFilterProxy"))
        
        if text == "Show: Manual":
            proxy.set_manual_filter(True)
        else:
            status = _STATUS_FILTER_MAP.get(text)
            proxy.set_status_filter(status)

    def _on_class_filter_changed(self, text: str) -> None:
        """Update the table filter when the class combo changes."""
        proxy = self._detection_table.model()
        if not isinstance(proxy, DetectionFilterProxy):
            return
        
        if text == "Class: All":
            proxy.set_class_filter(None)
        else:
            proxy.set_class_filter(text)

    # TODO: The below needs attention.
    def _populate_class_filter(self) -> None:
        """
        Populate the class filter combo box from the ValidationModel's label
        set. Called once when a session is opened.
        TODO: Will need to be called again if the detection set is modified
        """
        self._class_filter_combo.blockSignals(True)

        self._class_filter_combo.clear()
        self._class_filter_combo.addItem("Class: All")

        if self._validation_model is not None:
            for label in sorted(self._validation_model.labels):
                self._class_filter_combo.addItem(label)

        self._class_filter_combo.blockSignals(False)


    # --- Adding detections ---
    def _toggle_add_mode(self) -> None:
        """Toggle 'add detection' mode on or off."""
        self._add_btn.setChecked(not self._add_btn.isChecked())
    
    def _on_add_mode_toggled(self, checked: bool) -> None:
        """Enter or exit 'add detection' mode."""
        self._add_mode = checked
        self._viewer.set_add_mode(checked)

        if checked:
            self._show_status(
                "Add detection mode: click on the video frame to place a " \
                "detection."
            )
        else:
            self._clear_status()

    def _on_frame_clicked_for_add(
        self, frame_x: float, frame_y: float
    ) -> None:
        """Handle a click on the video frame in add mode."""
        if self._validation_model is None:
            return
        if self._active_source_file is None:
            return
        
        # --- Ask the user to pick a class label ---
        labels = sorted(self._validation_model.labels)
        if not labels:
            self._show_status("No labels available - open a session first")
            # TODO: It should also be possible to manually add labels at this stage (i.e. manually define a new label)
            return
        
        label, ok = QInputDialog.getItem(
            self,
            "Detection Label",
            "Select a class for this detection:",
            labels,
            current=0,
            editable=False, # TODO: Does making editable True allow for a user to add a new class? It sould need to also be added to the set.
        )
        if not ok:
            # User cancelled - exit add mode without creating anything
            self._add_btn.setChecked(False)
            return

        # use the current frame number
        current_frame = self._current_frame

        # Compute timestamp if metadata is available
        timestamp = 0.0
        if self._metadata and self._metadata.fps > 0:
            timestamp = current_frame / self._metadata.fps  

        # Default bounding box size - currently adding a detection simply adds a
        # default 60x60 box to verify that the system works. TODO: This will be
        # refined to include custom bounding box drawing with click and drag.
        default_width = 60.0
        default_height = 60.0

        vd = self._validation_model.add_detection(
            source_file=self._active_source_file,
            frame_number=current_frame,
            xc=frame_x, yc=frame_y,
            width=default_width, height=default_height,
            timestamp=timestamp,
            label=label,
        )

        # Uncheck the add button
        self._add_btn.setChecked(False)

        # refresh the frame to show the added detection
        self._request_frame.emit(current_frame)


    # --- Error handling and shutdown ---
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
