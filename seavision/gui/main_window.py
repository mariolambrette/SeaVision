"""Main application window."""

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import(
    QFileDialog,
    QMainWindow,
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

        file_menu = self.menuBar().addMenu("&File")

        # Open video
        open_video = QAction("Open &Video...", self)
        open_video.setShortcut(QKeySequence("Ctrl+O"))
        open_video.triggered.connect(self._on_open_video)
        file_menu.addAction(open_video)

        # Open Session
        open_session = QAction("Open &Session...", self)
        open_session.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_session.triggered.connect(self._on_open_session)
        file_menu.addAction(open_session)

        # Separator
        file_menu.addSeparator()

        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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
        
        # Step 2: Pick the video directory
        video_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Video Directory",
            str(Path.home()),
        )
        if not video_dir:
            return
        
        # Step 3: Pass both to the validation tab
        self._validation_tab.open_session(csv_path, video_dir)

        # Step 4: Update the status bar with session summary
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

    def closeEvent(self, event):
        """Ensure the worker thread is shutdown before closing."""
        self._validation_tab.shutdown()
        event.accept()
