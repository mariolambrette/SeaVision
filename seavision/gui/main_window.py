"""Main application window."""

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import(
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

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

        # Save session as
        save_session_as = QAction("Save Session &As...", self)
        save_session_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_session_as.triggered.connect(
            lambda: self._on_save_session(save_as=True)
        )
        file_menu.addAction(save_session_as)

        # Save session
        save_session = QAction("&Save Session...", self)
        save_session.setShortcut(QKeySequence("Ctrl+S"))
        save_session.triggered.connect(self._on_save_session)
        file_menu.addAction(save_session)

        # Load session
        load_session = QAction("&Load Session...", self)
        load_session.setShortcut(QKeySequence("Ctrl+L"))
        load_session.triggered.connect(self._on_load_session)
        file_menu.addAction(load_session)

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

        clear_cache = QAction("Clear Video &Cache...", self)
        clear_cache.triggered.connect(self._on_clear_cache)
        tools_menu.addAction(clear_cache)

    def _on_open_video(self) -> None:
        """Show file dialog and open th selected video."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            str(Path.home()),
            "Video files (*.ts *.TS *.mp4 *.MP4 *.avi *.AVI *.mkv *.MKV *.mov *.MOV);;All files (*)",
        )
        if filepath:
            self._validation_tab.open_video(filepath)
            self.statusBar().showMessage(f"Opened: {filepath}")

    def _on_open_session(self) -> None:
        """Show dialogs to open a detection CSV and video directory."""
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
            
        from seavision.gui.validation.session import SessionManager

        try:
            SessionManager.save_session(
                path,
                tab._validation_model,
                tab._csv_path,
                tab._video_dir,
                aws_profile=tab._aws_profile,
            )
            tab._session_save_path = Path(path)
            tab._has_unsaved_changes = False
            self.statusBar().showMessage(f"Session saved: {path}")
        except Exception as e:
            QMessageBox.warning(
                self, "Save Error",
                f"Failed to save session:\n\n{e}",
            ) 

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
        
        from seavision.gui.validation.session import SessionManager

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
        tab.open_session(csv_path, video_dir)

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

            tab._session_save_path = Path(path)
            tab._has_unsaved_changes = False
            tab._aws_profile = session_data.get("aws_profile")

            msg = (
                f"Session loaded: {stats['applied']} review actions restored."
            )
            if stats["manual_added"] > 0:
                msg += f", {stats['manual_added']} manual detections"
            if stats["skipped"] > 0:
                msg += f" ({stats['skipped']} skipped — CSV may have changed)"
            self.statusBar().showMessage(msg)

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


    def closeEvent(self, event):
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
