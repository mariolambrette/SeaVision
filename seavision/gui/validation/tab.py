"""
Validation tab - assembles viewer, transport and worker and creates the tab 
layout.
"""

import logging
from pathlib import Path

from PySide6.QtCore import (
    QThread, 
    QTimer, 
    QObject,
    QSettings,
    Qt, 
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
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
from seavision.gui.validation.button_styles import ReviewButtonStyles
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
from seavision.gui.validation.video_cache import S3VideoCache
from seavision.gui.validation.video_list import VideoListWidget
from seavision.gui.validation.video_viewer import FrameDisplay
from seavision.gui.validation.video_worker import VideoDecoderWorker
from seavision.engine.visualiser import (
    CSVDetectionLoader,
    ListDetectionSource,
)
from seavision.engine.detectors import Detection
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


class _S3DownloadWorker(QObject):
    """
    Background worker for downloading S3 videos.

    Reports progress per-file rather than per-byte — this avoids
    reliability issues with boto3's Callback parameter across
    versions and transfer strategies.
    """

    # Emitted after each file: (completed_count, total_count)
    progress = Signal(int, int)

    # Emitted after each successful file: (s3_uri, local_path)
    file_complete = Signal(str, str)

    # Emitted when all downloads are done: (success_count, fail_count)
    finished = Signal(int, int)

    # Emitted on each failure: (s3_uri, error_message)
    error = Signal(str, str)

    def __init__(self, cache, parent=None):
        super().__init__(parent)
        self._cache = cache
        self._cancelled = False

    def cancel(self):
        """Request cancellation of remaining downloads."""
        self._cancelled = True

    def download_batch(
        self,
        s3_uris: list[str],
        profile_name: str | None = None,
    ) -> None:
        """
        Download a list of S3 URIs to the local cache.

        Emits file_complete after each successful download, error
        after each failure, progress after each attempt (success or
        failure), and finished when all are done.
        """
        total = len(s3_uris)
        success = 0
        failed = 0

        for i, uri in enumerate(s3_uris):
            if self._cancelled:
                break

            try:
                local_path = self._cache.get_or_download(
                    uri, profile_name=profile_name,
                )
                self.file_complete.emit(uri, str(local_path))
                success += 1

            except Exception as e:
                self.error.emit(uri, str(e))
                failed += 1

            # Report progress after each file (success or failure)
            self.progress.emit(i + 1, total)

        self.finished.emit(success, failed)


class _StatusFilteredDetectionSource:
    """
    Adapter between ValidationModel and the video worker.

    Implements the DetectionSource interface (get_detections_for_frame) while
    filtering by review status and attaching per-detection colour hints for the
    annotator.

    Thread safety: This object is read by the worker thread and written
    (show_rejected toggle) by the main thread. The shared state is a sinle
    boolean, which is atomic under the GIL. No lock is needed.
    """

    # BGR colours for each status
    _STATUS_COLOURS = {
        ValidationStatus.PENDING:   (0, 0, 255),     # Red
        ValidationStatus.CONFIRMED: (0, 200, 0),     # Green
        ValidationStatus.CORRECTED: (0, 200, 0),     # Green
        ValidationStatus.REJECTED:  (128, 128, 128), # Grey
        ValidationStatus.SKIPPED:   (128, 128, 128), # Grey
    }

    def __init__(
        self,
        model: ValidationModel,
        source_file: str,
    ) -> None:
        self._model = model
        self._source_file = source_file
        self._show_rejected = False,
        self._show_all = True # When False hide all overlays

    @property
    def show_rejected(self) -> bool:
        return self._show_rejected
    
    @show_rejected.setter
    def show_rejected(self, value: bool) -> None:
        self._show_rejected = value

    @property
    def show_all(self) -> bool:
        return self._show_all
    
    @show_all.setter
    def show_all(self, value: bool) -> None:
        self._show_all = value

    def get_detections_for_frame(
            self, frame_number: int
    ) -> list[Detection]:
        """
        Return detections for a frame, filtered by status.

        Each returned Detection has an additional `_render_colour` attribute
        (a BGR tupple) set based on its review status. Rejected and skipped
        detections are excluded unless show_rejected is True.
        """
        if not self._show_all:
            return []
        
        validated = self._model.get_detections_for_frame(
            self._source_file, frame_number
        )

        result = []
        for vd in validated:
            # Filter rejected and skipped unless toggled on
            if vd.status in (
                ValidationStatus.REJECTED,
                ValidationStatus.SKIPPED,
            ) and not self._show_rejected:
                continue

            det = vd.detection

            # Attach a render colour based on status
            det._render_colour = self._STATUS_COLOURS.get(
                vd.status, (0, 0, 255)
            )
            result.append(det)

        return result


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
    _set_playback_speed = Signal(float) # Playback speed multiplier

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
        self._confirm_btn.setStyleSheet(ReviewButtonStyles().confirm)
        self._confirm_btn.setToolTip(
            "Confirm selected detection (C)\n"
            "Shift+C to confirm all on this frame"
        )

        self._reject_btn = QPushButton("Reject (R)")
        self._reject_btn.setStyleSheet(ReviewButtonStyles().reject)
        self._reject_btn.setToolTip(
            "Reject selected detection (R)\n"
            "Shift+R to reject all on this frame"
        )
        self._reject_btn.setToolTip(
            "Reject selected detection (R)\n"
            "Shift+R to reject all on this frame"
        )

        self._skip_btn = QPushButton("Skip (S)")
        self._skip_btn.setStyleSheet(ReviewButtonStyles().skip)
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
        self._add_btn.setStyleSheet(ReviewButtonStyles().add)
        self._add_btn.setToolTip(
            "Add a new detection (A)\n"
            "Shift+A to add detection at cursor position"
        )
        self._add_btn.setCheckable(True)
        self._add_btn.setToolTip(
            "Toggle 'add detection' mode. When enabled, click on frame to add a detection."
        )
        self._add_btn.toggled.connect(self._on_add_mode_toggled)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setStyleSheet(ReviewButtonStyles().reject)
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

        # --- Video list widget ---
        self._video_list = VideoListWidget()
        self._outer_splitter.addWidget(self._video_list)

        # --- Video Viewer ---
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
        self._csv_path : str | None = None
        self._video_dir: str | None = None
        self._session_save_path: Path | None = None
        self._has_unsaved_changes: bool = False
        self._aws_profile: str | None = None
        self._cache_dir: str | None = None
        self._active_detection_adapter: _StatusFilteredDetectionSource | None = None
        self._video_is_preloaded: bool = False

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
        self._set_playback_speed.connect(self._worker.set_speed)

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
        self._transport.speed_changed.connect(self._set_playback_speed)

        # --- Connect detection table signals ---
        self._detection_table.detection_selected.connect(
            self._on_detection_selected
        )
        self._detection_table.context_action.connect(
            self._on_table_context_action
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

        # --- Conect video list signals ---
        self._video_list.video_selected.connect(self._on_video_selected)

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

        # --- Store session state ---
        self._csv_loader = loader
        self._video_paths = resolved
        self._csv_path = csv_path
        self._video_dir = video_dir
        self._session_save_path = None
        self._has_unsaved_changes = False
        self._cache_dir = None

        # --- Create validation model ---
        self._validation_model = ValidationModel(loader, parent=self)

        # --- Populate the class filter ---
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

        # --- Handle S3 downloads if needed ---
        if s3_sources:
            self._pending_loader = loader
            self._pending_csv_path = csv_path
            self._download_s3_videos(
                s3_sources,
                on_complete=self._on_s3_downloads_complete,
            )

            # If there are also local videos, finish setup now
            # with what we have — S3 videos get added when ready
            if resolved:
                self._finish_session_setup(csv_path, loader)
            return

        # --- No S3 sources — finish setup immediately ---
        self._finish_session_setup(csv_path, loader)

        logger.info(
            "Session opened: %s — %d sources, %d resolved",
            csv_path,
            len(loader.sources_in_file),
            len(resolved),
        )

    def _finish_session_setup(self, csv_path: str, loader) -> None:
        """
        Complete session setup after all video paths are resolved.

        Called directly for local-only sessions, or after S3 downloads
        complete for S3 sessions. The ValidationModel and its signal
        connections are already set up by open_session.
        """
        resolved = self._video_paths

        # --- Check we found at least one video ---
        if not resolved:
            local_expected = [
                Path(s).name for s in loader.sources_in_file
                if not s.startswith("s3://")
            ]
            s3_expected = [
                s for s in loader.sources_in_file
                if s.startswith("s3://")
            ]

            message = "No video files could be resolved.\n\n"
            if local_expected:
                message += (
                    "Expected local files:\n"
                    + "\n".join(f"  • {n}" for n in local_expected[:10])
                    + ("\n  ..." if len(local_expected) > 10 else "")
                    + "\n\n"
                )
            if s3_expected:
                message += (
                    f"{len(s3_expected)} S3 video(s) failed to download."
                )

            QMessageBox.warning(self, "No Videos Found", message)
            return

        # --- Populate video list sidebar ---
        video_info = []
        for source_file in self._validation_model.get_all_source_files():
            progress = self._validation_model.get_progress(source_file)
            video_info.append({
                "source_file": source_file,
                "total": progress["total"],
                "reviewed": progress["reviewed"],
                "available": source_file in self._video_paths,
            })
        self._video_list.set_videos(video_info)

        # --- Open the first available video ---
        first_source = next(
            (s for s in loader.sources_in_file if s in resolved),
            None,
        )
        if first_source is not None:
            self._open_video_for_source(first_source)

        logger.info(
            "Session setup complete: %d videos available",
            len(resolved),
        )

    def _on_s3_downloads_complete(self) -> None:
        """Called when background S3 downloads finish."""
        loader = self._pending_loader
        csv_path = self._pending_csv_path
        self._pending_loader = None
        self._pending_csv_path = None

        # Finish setup — video list, open first video
        self._finish_session_setup(csv_path, loader)

    def _open_video_for_source(self, source_name: str) -> None:
        """
        Open a specific source video with its detection overlay.

        Queries the ValidationModel for this video's detections and populates
        the table with ValidatedDetection objects.

        Args:
            source_name: The source_file value from the CSV.
        """
        # CLear existing status messages
        self._clear_status()
        
        local_path = self._video_paths.get(source_name)
        if local_path is None:
            logger.error(
                "No local path for source: %s", 
                source_name
            )
            return

        self._active_source_file = source_name

        # --- Send status-aware detection source to the worker ---
        self._active_detection_adapter = _StatusFilteredDetectionSource(
            self._validation_model,
            source_name,
        )
        self._set_detection_source.emit(self._active_detection_adapter)

        # --- Populate the detection table from the ValidationModel ---
        validated_dets = self._validation_model.get_detections_for_video(
            source_name
        ) 
        fps = self._metadata.fps if self._metadata else None
        self._detection_model.set_detections(validated_dets, fps=fps)

        has_detections = len(validated_dets) > 0
        self._transport.set_detection_nav_enabled(has_detections)

        # --- Clear selection state ---
        self._detail_panel.clear()
        self._selected_detection = None
        self._set_highlight.emit(None)

        # --- Open video
        preload = self._should_preload(local_path)
        self._request_open.emit(local_path, preload)
        self._video_is_preloaded = preload

        logger.info(
            "Opened source '%s' (%s) — %d detection frames",
            source_name,
            local_path,
            len(self._active_detection_adapter.get_frame_numbers_with_detections()),
        )

    def _on_video_selected(self, source_file: str) -> None:
        """
        Switch to a different video in the session.

        Called when the user clicks a video in the sidebar. Delegates to
        _open_video_for_source which handles the video-switching logic.
        """
        if source_file == self._active_source_file:
            return # Already viewing this video
        
        if source_file not in self._video_paths:
            self._show_status(f"Video not available: {source_file}")
            return

        self._open_video_for_source(source_file)

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

        # Clear session saving state
        self._csv_path = None
        self._video_dir = None
        self._session_save_path = None
        self._has_unsaved_changes = False
        self._video_list.clear()

        # Disable detection navigation buttons
        self._transport.set_detection_nav_enabled(False)

        # Disable review buttons
        self._confirm_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._remove_btn.setEnabled(False)

        preload = self._should_preload(filepath)
        self._request_open.emit(filepath, preload)
        self._video_is_preloaded = preload

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

        # Auto-select the first unreviewed detection
        if (self._validation_model is not None
                and self._active_source_file is not None):
            first = self._validation_model.get_next_unreviewed(
                self._active_source_file
            )
            if first is not None:
                row = self._find_row_for_detection(first)
                if row is not None:
                    self._detection_table.select_row(row)
            elif self._detection_model.detection_count() > 0:
                # All reviewed — select the first detection anyway
                self._detection_table.select_row(0)

    def _download_s3_videos(
            self, 
            s3_uris: list[str],
            on_complete: callable = None,
        ) -> None:
        """Download S3 videos to local cache with progress dialog."""
        cache_dir = self._cache_dir or self._get_cache_dir()
        cache = S3VideoCache(cache_dir=Path(cache_dir))

        # --- Check if any S3 videos still need downloading ---
        uncached_uris = []
        for uri in s3_uris:
            cached_path = cache.get_cached_path(uri)
            if cached_path is not None and Path(cached_path).exists():
                self._video_paths[uri] = str(cached_path)
            else:
                uncached_uris.append(uri)

        if not uncached_uris:
            self._show_status("All S3 videos loaded from local cache.")
            return # All videos already cached, no need to ask or download

        # Ask the user which AWS profile to use
        profile_name = self._ask_aws_profile()
        if profile_name is None:
            return
        self._aws_profile = profile_name
        
        # Show busy cursor during size calcualtion
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            total_bytes, need_download = cache.calculate_download_size(
                uncached_uris, profile_name=self._aws_profile
            )
        except RuntimeError as e:
            QMessageBox.warning(
                self, "S3 Access Error",
                f"Cannot access S3 videos:\n\n{e}",
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
        
        if not need_download:
            # All already cached
            for uri in uncached_uris:
                local_path = cache.cache_dir / cache._cache_key(uri)
                self._video_paths[uri] = str(local_path)
            return
        
        size_mb = total_bytes / (1024 * 1024)
        
        # --- Confirm s3 dowload and allow cache relocation ---
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle("Download S3 Videos")
        msg.setText(
            f"This session requires downloading {len(need_download)} "
            f"video(s) (~{size_mb:.1f} MB) from S3.\n\n"
            f"Cache location: {cache.cache_dir}\n\n"
            f"Continue?"
        )
        download_btn = msg.addButton(
            "Download", QMessageBox.ButtonRole.AcceptRole
        )
        change_btn = msg.addButton(
            "Change Location…", QMessageBox.ButtonRole.ActionRole
        )
        cancel_btn = msg.addButton(
            "Cancel", QMessageBox.ButtonRole.RejectRole
        )
        msg.setDefaultButton(download_btn)
        msg.exec()

        clicked = msg.clickedButton()

        if clicked == change_btn:
            new_dir = QFileDialog.getExistingDirectory(
                self,
                "Choose Cache Location",
                str(cache.cache_dir),
            )
            if not new_dir:
                return  # User cancelled the directory picker

            # Persist the new location and rebuild the cache object
            self._set_cache_dir(Path(new_dir))
            self._cache_dir = new_dir
            cache = S3VideoCache(cache_dir=Path(new_dir))

            # Re-check what's already cached in the new location
            need_download = []
            total_bytes = 0
            for uri in uncached_uris:
                cached_path = cache.get_cached_path(uri)
                if cached_path is not None and Path(cached_path).exists():
                    self._video_paths[uri] = str(cached_path)
                else:
                    need_download.append(uri)

            if not need_download:
                self._show_status("All S3 videos loaded from cache.")
                if on_complete is not None:
                    on_complete()
                return

            # Recalculate size for remaining downloads
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                total_bytes, need_download = cache.calculate_download_size(
                    need_download, profile_name=self._aws_profile
                )
            except RuntimeError as e:
                QMessageBox.warning(
                    self, "S3 Access Error",
                    f"Cannot access S3 videos:\n\n{e}",
                )
                return
            finally:
                QApplication.restoreOverrideCursor()

        elif clicked == cancel_btn or clicked is None:
            return

        # If nothing left to download after cache relocation check
        if not need_download:
            self._show_status("All S3 videos loaded from cache.")
            if on_complete is not None:
                on_complete()
            return
        
        # Add already cached URIs
        for uri in uncached_uris:
            if uri not in need_download and cache.is_cached(uri):
                local_path = cache.cache_dir / cache._cache_key(uri)
                self._video_paths[uri] = str(local_path)
        
        # Dowload remaining in background
        from PySide6.QtWidgets import QProgressDialog
        
        total_files = len(need_download)
        progress_dialog = QProgressDialog(
            f"Downloading video 0/{total_files}...",
            "Cancel", 0, total_files, self,
        )
        progress_dialog.setWindowTitle("S3 Download")
        progress_dialog.setMinimumDuration(0)

        self._s3_thread = QThread()
        self._s3_worker = _S3DownloadWorker(cache)
        self._s3_worker.moveToThread(self._s3_thread)

        def _update_download_progress(completed, total):
            progress_dialog.setValue(completed)
            progress_dialog.setLabelText(
                f"Downloading video {completed}/{total}..."
            )

        self._s3_worker.progress.connect(_update_download_progress)
        self._s3_worker.file_complete.connect(
            lambda uri, path: self._video_paths.update({uri: path})
        )
        self._s3_worker.error.connect(
            lambda uri, msg: logger.error(
                "S3 download failed: %s — %s", uri, msg
            )
        )

        def on_finished(success, failed):
            progress_dialog.close()
            self._s3_thread.quit()
            if failed > 0:
                QMessageBox.warning(
                    self, "Download Incomplete",
                    f"{failed} video(s) failed to download.\n"
                    f"They will be greyed out in the video list.",
                )
            if on_complete is not None:
                on_complete()

        self._s3_worker.finished.connect(on_finished)
        progress_dialog.canceled.connect(self._s3_worker.cancel)

        self._s3_thread.started.connect(
            lambda: self._s3_worker.download_batch(
                need_download, profile_name=profile_name
            )
        )
        self._s3_thread.start()

    def _ask_aws_profile(self) -> str | None:
        """
        Ask the user which AWS profile to use for S3 access.

        Discovers profiles from ~/.aws/config and presents them in a dropdown.
        Returns the selected profile name, or None if cancelled.
        """
        # Discover configured profiles
        profiles = self._get_aws_profiles()

        if not profiles:
            QMessageBox.warning(
                self,
                "No AWS Profiles Found",
                "No AWS profiles are configured on this machine.\n\n"
                "To set up a profile, run:\n"
                "  aws configure sso\n\n"
                "See the AWS setup documentation for details.",
            )
            return None
        
        # Let the user pick which profile to use
        # TODO: Add an 'add profile' button which lets the users interactively
        #       set up an AWS profile.
        profile, ok = QInputDialog.getItem(
            self,
            "AWS Profile",
            "Select the AWS profile to use for S3 access:",
            profiles,
            current=0,
            editable=False,
        )

        if not ok:
            return None
        return profile
    
    @staticmethod
    def _get_aws_profiles() -> list[str]:
        """
        Read availble AWS profile names from ~/.aws/config.

        Returns a list of profile names. The default profile (if it exists) is 
        listed first.
        """
        # TODO: It might be useful to have functionality here for the user to
        #       adjust the search path depending on their machine's setup.
        config_path = Path.home() / ".aws" / "config"
        if not config_path.exists():
            return []

        import configparser

        config = configparser.ConfigParser()
        config.read(str(config_path))

        profiles = []
        for section in config.sections():
            # AWS config sections are named [profile foo] or [default]
            if section == "default":
                profiles.insert(0, "default")
            elif section.startswith("profile "):
                profiles.append(section[len("profile "):])

        return profiles
    
    @staticmethod
    def _get_cache_dir() -> Path:
        """
        Read the user's preferred cache directory from QSettings,
        falling back to the default ~/.seavision/cache/.
        """
        settings = QSettings("SeaVision", "SeaVision")
        saved = settings.value("s3CacheDir")
        if saved and Path(saved).is_dir():
            return Path(saved)
        return Path.home() / ".seavision" / "cache"
    
    @staticmethod
    def _set_cache_dir(path: Path) -> None:
        """Persist the user's preferred cache directory to QSettings."""
        settings = QSettings("SeaVision", "SeaVision")
        settings.setValue("s3CacheDir", str(path))

    def _refresh_video_list_availability(self) -> None:
        """Re-populate the video list with updated availability."""
        if self._validation_model is None:
            return

        video_info = []
        for source_file in self._validation_model.get_all_source_files():
            progress = self._validation_model.get_progress(source_file)
            video_info.append({
                "source_file": source_file,
                "total": progress["total"],
                "reviewed": progress["reviewed"],
                "available": source_file in self._video_paths,
            })
        self._video_list.set_videos(video_info)

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
        """
        User is dragging the slider — update the display.

        For pre-loaded videos, send the frame request immediately
        (array lookup is O(1)). For non-preloaded videos, debounce
        to avoid overwhelming cv2.VideoCapture with rapid seeks.
        """
        if self._is_playing:
            self._request_stop.emit()
            self._is_playing = False
            self._transport.set_playing(False)

        if self._video_is_preloaded:
            # Instant response for pre-loaded videos
            self._request_frame.emit(frame_number)
        else:
            # Debounce for disk-based seeking
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

    # --- Detection status view update ---
    def set_overlays_visible(self, visible: bool) -> None:
        """Toggle all detection overlays on or off."""
        if self._active_detection_adapter is not None:
            self._active_detection_adapter.show_all = visible
        # Re-render the current frame
        if self._metadata is not None and not self._is_playing:
            self._request_frame.emit(self._current_frame)

    def set_rejected_visible(self, visible: bool) -> None:
        """Toggle visibility of rejected and skipped detections."""
        if self._active_detection_adapter is not None:
            self._active_detection_adapter.show_rejected = visible
        if self._metadata is not None and not self._is_playing:
            self._request_frame.emit(self._current_frame)

    # --- Detection status ---
    def _on_detection_status_changed(
        self, detection_id: int, new_status: ValidationStatus
    ) -> None:
        """
        Handle a detection's status changing.

        Finds the row in the table model and emits dataChanged so the view
        repaints that row with updated status and colours.
        """
        self._has_unsaved_changes = True

        main_window = self.window()
        if hasattr(main_window, 'update_title'):
            main_window.update_title()
        
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

        # Re-render the current frame to update box colours
        if self._metadata is not None and not self._is_playing:
            self._request_frame.emit(self._current_frame)

    def _on_progress_changed(self, progress: dict) -> None:
        """Update the status bar with progress."""
        if self._active_source_file is None:
            return
        
        # Update the video list sidebar
        self._video_list.update_progress(
            self._active_source_file, progress
        )
        
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
        self._has_unsaved_changes = True
        
        if vd.detection.source_file == self._active_source_file:
            self._detection_model.append_detection(vd)
            self._select_validated_detection(vd)
            self._refresh_worker_detection_source()
            self._request_frame.emit(self._current_frame)

    def _on_detection_removed(self, detection_id: int) -> None:
        """Handle a manual detection being removed (implemented in Step 7)."""
        self._has_unsaved_changes = True
        
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
        """
        Advance to the next unreviewed detection. If no more detections in this
        video are unreviewed, move onto the next video in the list.
        """
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
            # Move onto next video
            advanced = self._advance_to_next_video()
            if not advanced:
                self._show_status(
                    "All detections reviewed."
                )

    def _advance_to_next_video(self) -> bool:
        """
        Advance to the next video that has unreviewed detections.

        Searches all videos in the session (starting after the current one) for
        any with PENDING detections. If found, switches to that video and
        selects its first unreviewed detection.

        Returns:
            True if video with unreviewed detections was found and loaded, False
            if all videos are fully reviewed.
        """
        if self._validation_model is None:
            return False
        
        all_sources = self._validation_model.get_all_source_files()
        if not all_sources:
            return False
        
        # Find current video's position in the list
        try:
            current_idx = all_sources.index(self._active_source_file)
        except ValueError:
            current_idx = -1

        # Search forward from the next video, wrapping around
        for offset in range(1, len(all_sources)):
            idx = (current_idx + offset) % len(all_sources)
            source = all_sources[idx]

            # Skip videos that aren't available locally
            if source not in self._video_paths:
                continue

            # Check if this video has unreviewed detections
            next_vd = self._validation_model.get_next_unreviewed(source)
            if next_vd is not None:
                # Switch to this video
                self._video_list.select_video(source)
                # The video_selected signal will fire, which calls
                # _on_video_selected -> _open_video_for_source.
                # The auto-select in Step 7 will pick the first
                # unreviewed detection.
                return True

        return False

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

    # --- Context menu handlers ---
    def _on_table_context_action(
        self, action_name: str, source_row: int
    ) -> None:
        """Handle a context menu action from the detection table."""
        vd = self._detection_model.detection_at(source_row)
        if vd is None:
            return

        if action_name == "confirm":
            self._validation_model.set_status(
                vd.id, ValidationStatus.CONFIRMED
            )
        elif action_name == "reject":
            self._validation_model.set_status(
                vd.id, ValidationStatus.REJECTED
            )
        elif action_name == "skip":
            self._validation_model.set_status(
                vd.id, ValidationStatus.SKIPPED
            )
        elif action_name == "remove":
            self._validation_model.remove_detection(vd.id)
        elif action_name == "select":
            self._select_validated_detection(vd)


    # --- Error handling and shutdown ---
    def _on_error(self, message: str) -> None:
        """Worker reported an error."""
        logger.warning("Worker error: %s", message)
        self._show_status(f"⚠ {message}")
        QMessageBox.warning(self, "Video Error", message)

    def shutdown(self) -> None:
        """
        Stop playback, close video and shut down the worker thread.

        Must be called before the application exits, otherwise the background
        thread may hang or print warnings.
        """
        # Clean up S3 download thread if running
        if hasattr(self, '_s3_thread') and self._s3_thread.isRunning():
            self._s3_worker.cancel()
            self._s3_thread.quit()
            self._s3_thread.wait()

        self._request_stop.emit()
        self._clear_detection_source.emit()
        self._request_close.emit()
        self._thread.quit()
        self._thread.wait()
