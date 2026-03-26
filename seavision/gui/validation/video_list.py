"""
Video list sidebar widget.

Shows all videos in the current session with detection counts and review
progress. Clicking a video switched the viewer and detection table to that
video.
"""

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

_COLOUR_NOT_STARTED = QColor(150, 150, 150) # GREY
_COLOUR_IN_PROGRESS = QColor("#CC7A00")  # AMBER/ORANGE
_COLOUR_COMPLETE = QColor(60, 160, 60)      # GREEN
_COLOUR_UNAVAILABLE = QColor(180, 180, 180)  # LIGHT GREY for videos that can't be loaded (e.g. missing S3 creds)


class VideoListWidget(QWidget):
    """
    Sidebar showing all videos in the current session.

    Signals:
        video_selected: Emitted when the users clicks a video. Carries the
            source_file string.
    """

    video_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Main layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        # --- Header ---
        self._header = QLabel("Videos:")
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._header)

        # --- Video list ---
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list)

    def set_videos(self, video_info: list[dict]) -> None:
        """
        Populate the list with video entries.

        Args:
            video_info: List of dicts with keys:
                source_file, total, rviewed, available.
        """
        self._list.blockSignals(True)
        self._list.clear()

        for info in video_info:
            source_file = info["source_file"]
            filename = Path(source_file).name
            total = info["total"]
            reviewed = info["reviewed"]
            available = info.get("available", True)

            text = f"{filename} ({reviewed}/{total})"
            item = QListWidgetItem(text)
            item.setToolTip(source_file)
            item.setData(Qt.ItemDataRole.UserRole, source_file)

            if not available:
                item.setForeground(QBrush(_COLOUR_UNAVAILABLE))
                item.setFlags(
                    item.flags() & ~Qt.ItemFlag.ItemIsEnabled
                )
                item.setToolTip(f"{source_file} (not found)")
            elif reviewed == 0:
                item.setForeground(QBrush(_COLOUR_NOT_STARTED))
            elif reviewed >= total:
                item.setForeground(QBrush(_COLOUR_COMPLETE))
            else:
                item.setForeground(QBrush(_COLOUR_IN_PROGRESS))

            self._list.addItem(item)

        self._list.blockSignals(False)
        self._header.setText(f"Videos ({len(video_info)}):")

    def update_progress(
        self, source_file: str, progress: dict
    ) -> None:
        """Update the progress display for a single video."""
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) != source_file:
                continue

            total = progress["total"]
            reviewed = progress["reviewed"]
            filename = Path(source_file).name
            item.setText(f"{filename} ({reviewed}/{total})")

            if reviewed == 0:
                item.setForeground(QBrush(_COLOUR_NOT_STARTED))
            elif reviewed >= total:
                item.setForeground(QBrush(_COLOUR_COMPLETE))
            else:
                item.setForeground(QBrush(_COLOUR_IN_PROGRESS))
            break

    def _on_item_changed(
            self, 
            current: QListWidgetItem, 
            _previous: QListWidgetItem,
        ) -> None:
        if current is None:
            return
        source_file = current.data(Qt.ItemDataRole.UserRole)
        if source_file:
            self.video_selected.emit(source_file)

    def select_video(self, source_file: str) -> None:
        """Programmatically select a video in the list."""
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == source_file:
                self._list.setCurrentItem(item)
                return

    def clear(self) -> None:
        self._list.clear()
        self._header.setText("Videos:")
