"""Main application window."""

from os import path
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import(
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget
)

from seavision.gui.validation.session import SessionManager
from seavision.gui.validation.tab import ValidationTab


class MainWindow(QMainWindow):
    """
    Top-level window for the SeaVision GUI application.

    Contains a tab widget (currently just the validation tab), a menu bar with
    file operations, and a status bar.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SeaVision")
        self.resize(1200, 800)

        # --- Central widget ---
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # --- Validation tab ---
        self._validation_tab = ValidationTab()
        self._tabs.addTab(self._validation_tab, "Validation")

        # --- Menu bar ---
        self._build_menus()

        # --- Status bar ---
        self.statusBar().showMessage("Ready")

        self._restore_settings()

        # --- Drag & drop ---
        self.setAcceptDrops(True)

    def _build_menus(self):
        """Create the File menu."""

        # --- File Meanu ---
        file_menu = self.menuBar().addMenu("&File")

        # Open video
        open_video = QAction("Open &Video...", self)
        open_video.setShortcut(QKeySequence("Ctrl+O"))
        open_video.triggered.connect(self._on_open_video)
        file_menu.addAction(open_video)

        file_menu.addSeparator()

        # Open a new Session
        open_session = QAction("&New Session...", self)
        open_session.setShortcut(QKeySequence("Ctrl+N"))
        open_session.triggered.connect(self._on_open_session)
        file_menu.addAction(open_session)

        file_menu.addSeparator()

        # Open S3 Video
        open_s3_video = QAction("Open Video from S&3...", self)
        open_s3_video.triggered.connect(self._on_open_s3_video)
        file_menu.addAction(open_s3_video)

        # New S3 Session
        open_s3_session = QAction("New Session from S3...", self)
        open_s3_session.triggered.connect(self._on_open_s3_session)
        file_menu.addAction(open_s3_session)

        file_menu.addSeparator()

        # Load session
        load_session = QAction("&Load Session...", self)
        load_session.setShortcut(QKeySequence("Ctrl+L"))
        load_session.triggered.connect(self._on_load_session)
        file_menu.addAction(load_session)

        # Recent sessions
        self._recent_menu = file_menu.addMenu("&Recent Sessions")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        # Save session
        save_session = QAction("&Save Session...", self)
        save_session.setShortcut(QKeySequence("Ctrl+S"))
        save_session.triggered.connect(self._on_save_session)
        file_menu.addAction(save_session)

        # Save session as
        save_session_as = QAction("Save Session &As...", self)
        save_session_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_session_as.triggered.connect(
            lambda: self._on_save_session(save_as=True)
        )
        file_menu.addAction(save_session_as)

        file_menu.addSeparator()

        # Export reviewed detections
        export_action = QAction("&Export Validated Detections...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        # Separator
        file_menu.addSeparator()

        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Tools menu ---
        tools_menu = self.menuBar().addMenu("&Tools")

        set_cache_loc = QAction("Set Video Cache &Location...", self)
        set_cache_loc.triggered.connect(
            self._on_set_cache_location
        )
        tools_menu.addAction(set_cache_loc)

        clear_cache = QAction("Clear Video &Cache...", self)
        clear_cache.triggered.connect(self._on_clear_cache)
        tools_menu.addAction(clear_cache)

        # --- View menu ---
        view_menu = self.menuBar().addMenu("&View")

        self._toggle_overlays = QAction("Show &Detections", self)
        self._toggle_overlays.setCheckable(True)
        self._toggle_overlays.setChecked(True)
        self._toggle_overlays.setShortcut(QKeySequence("Ctrl+D"))
        self._toggle_overlays.toggled.connect(
            self._validation_tab.set_overlays_visible
        )
        view_menu.addAction(self._toggle_overlays)

        self._toggle_rejected = QAction(
            "Show &Rejected Detections", self
        )
        self._toggle_rejected.setCheckable(True)
        self._toggle_rejected.setChecked(False)
        self._toggle_rejected.toggled.connect(
            self._validation_tab.set_rejected_visible
        )
        view_menu.addAction(self._toggle_rejected)

    
    # --- OPEN VIDEO/SESSION HANDLERS ---
    def _unsaved_changes_warning(self) -> bool:
        """
        Check for unsaved changes when opening a new video/session.

        Returns:
            True if it's safe to proceed (no unsaved changes or user chose to
            discard/save), False if the user cancelled.
        """
        tab = self._validation_tab
        if tab is not None and tab._has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved review progress.\n\n"
                "Do you want to save before opening a new session?",
                (
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel
                ),
                QMessageBox.StandardButton.Save,
            )

            if reply == QMessageBox.StandardButton.Save:
                self._on_save_session()
                if tab._has_unsaved_changes:
                    return False  # Save was cancelled or failed
            elif reply == QMessageBox.StandardButton.Cancel:
                return False

        return True  # No unsaved changes, or user saved/discarded

    def _on_open_video(self) -> None:
        """Show file dialog and open th selected video."""
        # Check for any unsaved changes
        if not self._unsaved_changes_warning():
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            str(Path.home()),
            "Video files (*.ts *.TS *.mp4 *.MP4 *.avi *.AVI *.mkv *.MKV *.mov *.MOV);;All files (*)",
        )
        if filepath:
            self._validation_tab.open_video(filepath)
            self.statusBar().showMessage(f"Opened: {filepath}")
            self.update_title()

    def _on_open_session(self) -> None:
        """Show dialogs to open a detection CSV and video directory."""
        # Check for any unsaved changes
        if not self._unsaved_changes_warning():
            return
        
        # Step 1: Pick the CSV file
        csv_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Detection CSV",
            str(Path.home()),
            "CSV files (*.csv);;All files (*.*)",
        )
        if not csv_path:
            return
        
        # Step 2: Peek at the CSV to determine if we need a video directory.
        # If all sources are S3 URIs, we don't need to ask for a local directory
        try:
            from seavision.engine.visualiser import CSVDetectionLoader
            loader = CSVDetectionLoader(csv_path)
        except (FileNotFoundError, ValueError) as e:
            QMessageBox.warning(
                self, "CSV Error",
                f"Failed to read detection CSV:\n\n{e}",
            )
            return
        
        # Classify sources
        local_sources = [
            s for s in loader.sources_in_file
            if not s.startswith("s3://")
        ]
        s3_sources = [
            s for s in loader.sources_in_file
            if s.startswith("s3://")
        ]

        # Step 3: Only ask for a video directory if there are local sources
        video_dir = ""
        if local_sources:
            video_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Video Directory",
                str(Path.home()),
            )
            if not video_dir:
                # User cancelled — but if there are S3 sources, we can
                # still proceed with just those
                if not s3_sources:
                    return
                # Proceed with S3-only sources, no local directory
                video_dir = ""
        
        # Step 4: Pass both to the validation tab
        self._validation_tab.open_session(csv_path, video_dir)

        # Step 5: Update the status bar with session summary
        self._update_session_status()

        # Step 6: Update the window title
        self.update_title()

    def _on_open_s3_video(self) -> None:
        """Open a single video file from S3 (no detections)."""
        from seavision.gui.validation.s3_browser import S3BrowserMode

        dialog = self._open_s3_browser(S3BrowserMode.VIDEO)
        if dialog is None:
            return
        
        video_uri = dialog.selected_video_uri
        profile = dialog.selected_profile
        if not video_uri:
            return
        
        self._validation_tab._aws_profile = profile

        local_path = self._s3_download_to_cache(video_uri, profile)
        if local_path is None:
            self.statusBar().showMessage("S3 video download failed")
            return
        
        self._validation_tab.open_video(local_path)
        self.statusBar().showMessage(f"Opened S3 video: {video_uri}")



    def _on_open_s3_session(self) -> None:
        """Open a detection session from S3 (CSV + video directory)."""
        from seavision.gui.validation.s3_browser import S3BrowserMode

        dialog = self._open_s3_browser(S3BrowserMode.SESSION)
        if dialog is None:
            return
        
        csv_uri = dialog.selected_csv_uri
        video_prefix = dialog.selected_video_prefix
        profile = dialog.selected_profile
        if not csv_uri or not video_prefix:
            return
        
        self._validation_tab._aws_profile = profile

        # Download the CSV to local cache to open_session can parse it
        local_csv = self._s3_download_to_cache(csv_uri, profile)
        if local_csv is None:
            self.statusBar().showMessage("S3 CSV download failed")
            return
        
        # video_prefix is an S3 URI like "s3://bucket/videos/" —
        # open_session → resolve_video_paths classifies every source
        # from the CSV as an S3 source, and _download_s3_videos
        # handles the caching.
        self._validation_tab.open_session(
            csv_path=local_csv,
            video_dir=video_prefix,
        )
        self._update_session_status()

    # --- OPEN FROM S3 DIALOGS ---
    def _open_s3_browser(self, mode):
        """
        Open the S3 browser dialog in the given mode and return the dialog if
        accepted, or None if cancelled.

        Checks for AWS profiles first and shows an error if none are found.

        Args:
            mode: S3BrowserMode.VIDEO or S3BrowserMode.SESSION

        Returns:
            The accepted S3BrowserDialog, or None.
        """
        from seavision.gui.validation.s3_browser import S3BrowserDialog

        profiles = self._validation_tab._get_aws_profiles()
        if not profiles:
            QMessageBox.warning(
                self,
                "No AWS Profiles",
                "No AWS profiles are configured on this machine.\n\n"
                "To set up a profile, run:\n"
                "  aws configure sso\n\n"
                "See docs/AWS_SETUP.md for details.", #TODO: This should be a link toonline doce or a proper local help document
            )
            return None
        
        dialog = S3BrowserDialog(profiles, mode, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        
        return dialog
    
    def _s3_download_to_cache(
        self, uri: str, profile: str
    ) -> str | None:
        """
        Download a single S3 URI to the local cache.

        Shows a busy cursor during the download and an error dialog on failure.

        Returns:
            The local file path as a string, or None on failure.
        """
        from PySide6.QtCore import Qt
        from seavision.gui.validation.video_cache import S3VideoCache

        cache = S3VideoCache(
            cache_dir = self._validation_tab._get_cache_dir()
        )

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            local_path = cache.get_or_download(
                uri, profile_name=profile
            )
            return str(local_path)
        except RuntimeError as e:
            QMessageBox.warning(
                self,
                "Download Error",
                f"Failed to download {uri}:\n\n{e}",
            )
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def _update_session_status(self) -> None:
        """Update the status bar with session information."""
        tab = self._validation_tab
        if tab._csv_loader is None:
            return
        
        total_detections = sum(
            len(tab._csv_loader.get_detections_for_frame(f))
            for f in tab._csv_loader.get_frame_numbers_with_detections()
        )
        video_count = len(tab._csv_loader.sources_in_file)
        resolved_count = len(tab._video_paths)

        csv_name = Path(str(tab._csv_loader.csv_path)).name

        self.statusBar().showMessage(
            f"{csv_name} — {total_detections} detections across "
            f"{video_count} videos ({resolved_count} found locally)"
        )

    def _on_save_session(self, save_as: bool = False) -> None:
        """Save the current session state."""
        tab = self._validation_tab
        if tab._validation_model is None:
            self.statusBar().showMessage("No session to save")
            return
        
        if tab._session_save_path is not None and not save_as:
            path = tab._session_save_path
        else:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Session",
                str(Path.home()),
                "SeaVision Session (*.seavision-session)",
            )
            if not path:
                return

        try:
            SessionManager.save_session(
                path,
                tab._validation_model,
                tab._csv_path,
                tab._video_dir,
                aws_profile=tab._aws_profile,
                cache_dir=str(tab._cache_dir) if tab._cache_dir else None,
            )
            tab._session_save_path = Path(path)
            tab._has_unsaved_changes = False
            self.statusBar().showMessage(f"Session saved: {path}")
        except Exception as e:
            QMessageBox.warning(
                self, "Save Error",
                f"Failed to save session:\n\n{e}",
            ) 
        
        self.update_title()
        self._add_recent_session(path)

    def _load_session_from_path(self, path: str) -> None:
        """Load a previously saved session from a specific path."""
        try:
            session_data = SessionManager.load_session(path)
        except (FileNotFoundError, ValueError) as e:
            QMessageBox.warning(
                self, "Load Error",
                f"Failed to load session:\n\n{e}",
            )
            return
        
        csv_path: str = session_data["csv_path"]
        video_dir: str = session_data["video_dir"]

        # Check that the csv still exists
        if not Path(csv_path).exists():
            csv_path, _ = QFileDialog.getOpenFileName(
                self,
                f"Locate CSV (was: {csv_path})",
                str(Path.home()),
                "CSV files (*.csv)",
            )
            if not csv_path:
                return

        # Check that the video directory still exists if local paths are present
        has_local_sources = video_dir and video_dir.strip()
        if has_local_sources and not Path(video_dir).is_dir():
            video_dir = QFileDialog.getExistingDirectory(
                self,
                f"Locate Video Directory (was: {video_dir})",
                str(Path.home()),
            )
            if not video_dir:
                return

        # Open the session from the CSV and video directory
        tab = self._validation_tab
        tab._aws_profile = session_data.get("aws_profile")

        loaded_cache_dir = session_data.get("cache_dir")
        if loaded_cache_dir and Path(loaded_cache_dir).is_dir():
            tab._cache_dir = Path(loaded_cache_dir)
        else:
            tab._cache_dir = None

        tab.open_session(csv_path, video_dir)

        tab._session_save_path = Path(path)

        # Apply saved state
        if tab._validation_model is not None:
            stats = SessionManager.apply_session_state(
                tab._validation_model, session_data
            )

            # Refresh the table to show restored statuses
            if tab._active_source_file:
                video_dets = tab._validation_model.get_detections_for_video(
                    tab._active_source_file
                )
                fps = tab._metadata.fps if tab._metadata else None
                tab._detection_model.set_detections(video_dets, fps)

            # Refresh video list progress
            for sf in tab._validation_model.get_all_source_files():
                progress = tab._validation_model.get_progress(sf)
                tab._video_list.update_progress(sf, progress)

            tab._has_unsaved_changes = False
            self.update_title()

            msg = (
                f"Session loaded: {stats['applied']} review actions restored."
            )
            if stats["manual_added"] > 0:
                msg += f", {stats['manual_added']} manual detections"
            if stats["skipped"] > 0:
                msg += f" ({stats['skipped']} skipped — CSV may have changed)"
            self.statusBar().showMessage(msg)

            self._add_recent_session(path)

    def _on_load_session(self) -> None:
        """Load a previously saved session."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            str(Path.home()),
            "SeaVision Session (*.seavision-session)",
        )
        if not path:
            return
        
        self._load_session_from_path(path)

    def _on_export(self) -> None:
        """Export confirmed detections to CSV."""
        tab = self._validation_tab
        if tab._validation_model is None:
            self.statusBar().showMessage("No session to export")
            return

        csv_name = (
            Path(tab._csv_path).stem if tab._csv_path else "detections"
        )
        default_name = f"{csv_name}_validated.csv"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Validated Detections",
            str(Path.home() / default_name),
            "CSV files (*.csv | *.CSV);;All files (*.*)",
        )
        if not path:
            return
        
        from seavision.gui.validation.session import SessionManager

        try:
            count = SessionManager.export_detections(
                path, tab._validation_model
            )
            self.statusBar().showMessage(
                f"Exported {count} confirmed detections to: {path}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Export Error",
                f"Failed to export detections:\n\n{e}",
            )

    # --- CACHE TOOL HANDLERS ---
    def _on_clear_cache(self) -> None:
        """Show cache size and offer to clear it."""
        from seavision.gui.validation.video_cache import S3VideoCache

        cache = S3VideoCache()
        size = cache.cache_size()
        size_mb = size / (1024 * 1024)

        if size == 0:
            QMessageBox.information(
                self, "Video Cache",
                "The video cache is empty.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Clear Video Cache",
            f"The video cache contains {size_mb:.1f} MB of data.\n\n"
            f"Location: {cache.cache_dir}\n\n"
            f"Clear it? Downloaded videos will need to be "
            f"re-downloaded next time.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            freed = cache.clear_cache()
            freed_mb = freed / (1024 * 1024)
            self.statusBar().showMessage(
                f"Cache cleared: {freed_mb:.1f} MB freed"
            )

    def _on_set_cache_location(self) -> None:
        """Let the user choose where S3 videos are cached."""
        tab = self._validation_tab
        current = tab._get_cache_dir()

        new_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose Video Cache Location",
            str(current)
        )
        if not new_dir:
            return
        
        tab._set_cache_dir(Path(new_dir))
        self.statusBar().showMessage(
            f"Cache location set to: {new_dir}"
        )

    def update_title(self) -> None:
        """
        Update the window title to reflect the current state.

        Format:
        - No session: "SeaVision"
        - Saved session: "SeaVision — session_name.seavision-session"
        - Unsaved changes: "SeaVision — session_name.seavision-session *"
        - CSV open but not saved: "SeaVision — detections.csv"
        """
        parts = ["SeaVision"]

        tab = self._validation_tab
        if tab._session_save_path is not None:
            parts.append("—")
            parts.append(tab._session_save_path.name)
        elif tab._csv_path is not None:
            parts.append("—")
            parts.append(Path(tab._csv_path).name)

        if tab._has_unsaved_changes:
            parts.append("*")

        self.setWindowTitle(" ".join(parts))

    # --- DRAG & DROP HANDLER OVERRIDES ---
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drag events for supported file types."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile().lower()
                if path.endswith(
                    (".csv", ".ts", ".mp4", ".avi", ".mkv",
                     ".seavision-session")
                ):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle dropped files."""
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            lower = path.lower()

            if lower.endswith(".seavision-session"):
                self._load_session_from_path(path)
                return

            if lower.endswith(".csv"):
                # Trigger the session flow — need to ask for video dir
                from seavision.engine.visualiser import CSVDetectionLoader

                try:
                    loader = CSVDetectionLoader(path)
                except (FileNotFoundError, ValueError) as e:
                    QMessageBox.warning(
                        self, "CSV Error",
                        f"Failed to read detection CSV:\n\n{e}",
                    )
                    return

                # Check if we need a video directory
                local_sources = [
                    s for s in loader.sources_in_file
                    if not s.startswith("s3://")
                ]

                video_dir = ""
                if local_sources:
                    video_dir = QFileDialog.getExistingDirectory(
                        self,
                        "Select Video Directory",
                        str(Path.home()),
                    )
                    if not video_dir:
                        return

                self._validation_tab.open_session(path, video_dir)
                self._update_session_status()
                return

            if lower.endswith((".ts", ".mp4", ".avi", ".mkv")):
                self._validation_tab.open_video(path)
                return

    # --- Save window state (size, splitter location etc) between sessions ---
    def _save_settings(self) -> None:
        """Persist window geometry and state."""
        from PySide6.QtCore import QSettings

        settings = QSettings("SeaVision", "SeaVision")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())

        # Save splitter positions from the validation tab
        tab = self._validation_tab
        if hasattr(tab, '_outer_splitter'):
            settings.setValue(
                "outerSplitter", tab._outer_splitter.saveState()
            )
        if hasattr(tab, '_right_splitter'):
            settings.setValue(
                "rightSplitter", tab._right_splitter.saveState()
            )

        # Save the playback speed
        if hasattr(tab, '_transport'):
            settings.setValue(
                "playbackSpeed",
                tab._transport._speed_combo.currentText()
            )

    # --- Restore saved settings from previous session ---
    def _restore_settings(self) -> None:
        """Restore window geometry and state from previous session."""
        settings = QSettings("SeaVision", "SeaVision")

        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        state = settings.value("windowState")
        if state is not None:
            self.restoreState(state)

        tab = self._validation_tab
        outer = settings.value("outerSplitter")
        if outer is not None and hasattr(tab, '_outer_splitter'):
            tab._outer_splitter.restoreState(outer)

        right = settings.value("rightSplitter")
        if right is not None and hasattr(tab, '_right_splitter'):
            tab._right_splitter.restoreState(right)

        speed = settings.value("playbackSpeed")
        if speed is not None and hasattr(tab, '_transport'):
            idx = tab._transport._speed_combo.findText(speed)
            if idx >= 0:
                tab._transport._speed_combo.setCurrentIndex(idx)

    # --- Handle recent session cache ---
    def _add_recent_session(self, path: str) -> None:
        """Add a session path to the recent sessions list."""

        settings = QSettings("SeaVision", "SeaVision")
        recent = settings.value("recentSessions", [])
        if not isinstance(recent, list):
            recent = []

        # Remove if already present (will re-add at top)
        if path in recent:
            recent.remove(path)

        recent.insert(0, path)
        recent = recent[:5]  # Keep at most 5

        settings.setValue("recentSessions", recent)
        self._rebuild_recent_menu()

    def _get_recent_sessions(self) -> list[str]:
        """Get the list of recent session paths."""

        settings = QSettings("SeaVision", "SeaVision")
        recent = settings.value("recentSessions", [])
        if not isinstance(recent, list):
            return []
        # Filter out paths that no longer exist
        return [p for p in recent if Path(p).exists()]
    
    def _rebuild_recent_menu(self) -> None:
        """Rebuild the Recent Sessions submenu."""
        self._recent_menu.clear()

        recent = self._get_recent_sessions()
        if not recent:
            no_recent = QAction("(no recent sessions)", self)
            no_recent.setEnabled(False)
            self._recent_menu.addAction(no_recent)
            return

        for path in recent:
            action = QAction(Path(path).name, self)
            action.setToolTip(str(path))
            action.setData(path)
            action.triggered.connect(self._on_open_recent)
            self._recent_menu.addAction(action)

        self._recent_menu.addSeparator()
        clear_action = QAction("Clear Recent Sessions", self)
        clear_action.triggered.connect(self._on_clear_recent)
        self._recent_menu.addAction(clear_action)

    def _on_open_recent(self) -> None:
        """Open a session from the recent sessions list."""
        action = self.sender()
        if action is None:
            return
        path = action.data()
        if path and Path(path).exists():
            self._load_session_from_path(path)
        else:
            QMessageBox.warning(
                self, "File Not Found",
                f"Session file no longer exists:\n{path}"
            )
            self._rebuild_recent_menu()

    def _on_clear_recent(self) -> None:
        """Clear the recent sessions list."""
        settings = QSettings("SeaVision", "SeaVision")
        settings.setValue("recentSessions", [])
        self._rebuild_recent_menu()

    def closeEvent(self, event):
        self._save_settings()
        
        tab = self._validation_tab

        if tab._has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved review progress.\n\n"
                "Do you want to save before closing?",
                (
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel
                ),
                QMessageBox.StandardButton.Save,
            )

            if reply == QMessageBox.StandardButton.Save:
                self._on_save_session()
                if tab._has_unsaved_changes:
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        tab.shutdown()
        event.accept()
