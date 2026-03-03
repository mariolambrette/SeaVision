"""SeaVision GUI application entry point."""

import sys

def main():
    """Launch the SeaVision GUI."""

    # Import PySide6 with error handling if not available
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is required for the GUI. "
            "Install with: pip install seavision[gui]"
        )
        sys.exit(1)
    
    app = QApplication(sys.argv)
    app.setApplicationName("SeaVision")

    # Placeholder — we'll build the main window next
    from PySide6.QtWidgets import QMainWindow, QLabel
    window = QMainWindow()
    window.setWindowTitle("SeaVision")
    window.setCentralWidget(QLabel("SeaVision — Validation tab coming soon"))
    window.resize(1200, 800)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
