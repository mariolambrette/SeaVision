"""Main application window."""

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
        super.__init__(parent)
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
            "",
            "Video files (*.mp4 *.avi *.mkv *.avi *.mov *.mts);;All files (*.*)",
        )
        if filepath:
            self._validation_tab.open_video(filepath)
            self.statusBar().showMessage(f"Opened: {filepath}")

    def closeEvent(self, event):
        """Ensure the worker thread is shutdown before closing."""
        self._validation_tab.shutdown()
        event.accept()
