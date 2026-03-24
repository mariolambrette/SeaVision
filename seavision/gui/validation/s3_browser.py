"""
S3 bucket browser dialog for opening sessions or videos from S3.
 
The dialog operates in one of two modes, set at construction time:
 
    S3BrowserMode.VIDEO
        The user browses and selects a single video file.
        The caller reads ``selected_video_uri`` after accept.
 
    S3BrowserMode.SESSION
        The user selects a detection CSV file and a video directory
        (S3 prefix). The caller reads ``selected_csv_uri`` and
        ``selected_video_prefix`` after accept.
 
Both modes share the same connection and navigation UI. The selection
panel at the bottom changes depending on the mode.
 
This module depends on boto3 (imported lazily inside the worker) and
PySide6.
"""

import logging
from enum import Enum, auto
from pathlib import PurePosixPath
 
from PySide6.QtCore import Qt, Signal, QThread, QObject, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)
 
logger = logging.getLogger(__name__)


_VIDEO_EXTENSIONS = frozenset({
    ".ts", ".mts", ".m2ts",
    ".mp4", ".m4v",
    ".avi",
    ".mkv",
    ".mov",
})

class S3BrowserMode(Enum):
    VIDEO = auto()
    SESSION = auto()


# --- Background worker - runs S3 list operations off the main thread ---
class _S3ListWorker(QObject):
    """
    Background worker for listing S3 bucket contents.

    Runs on a dedicated QThread so that network calls don't block the UI. Emits
    listing_ready with the results, or error_occurred on failure.
    """

    listing_ready = Signal(str, list)  # prefix, items
    error_occurred = Signal(str)       # error message

    @Slot(str, str, str)
    def list_prefix(
        self, bucket: str, prefix: str, profile: str
    ) -> None:
        """
        List objects and common prefixes under an S3 path.
 
        Each item in the emitted list is a dict with keys:
            key         — full S3 key (e.g. "videos/clip_001.ts")
            is_prefix   — True for directories, False for files
            display     — short display name (e.g. "clip_001.ts")
            size        — file size in bytes (files only)
        """
        try:
            import boto3

            session = boto3.Session(
                profile_name=profile if profile else None
            )
            s3 = session.client("s3")

            paginator = s3.get_paginator("list_objects_v2")
            items: list[dict] = []

            for page in paginator.paginate(
                Bucket=bucket, Prefix=prefix, Delimiter="/"
            ):
                # Directories (common prefixes)
                for cp in page.get("CommonPrefixes", []):
                    items.append({
                        "key": cp["Prefix"],
                        "is_prefix": True,
                        "display": PurePosixPath(
                            cp["Prefix"].rstrip("/")
                        ).name + "/",
                    })

                # Files (objects)
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key == prefix:
                        continue
                    items.append({
                        "key": key,
                        "is_prefix": False,
                        "display": PurePosixPath(key).name,
                        "size": obj.get("Size", 0),
                    })

            self.listing_ready.emit(prefix, items)

        except Exception as e:
            self.error_occurred.emit(str(e))


# --- Dialog ---
class S3BrowserDialog(QDialog):
    """
    Dialog for browsing an S3 bucket.
 
    The dialog operates in one of two modes (set via the ``mode``
    constructor parameter):
 
    **VIDEO mode** — the user selects a single video file.
    After accept, read ``selected_video_uri``.
 
    **SESSION mode** — the user selects a CSV and a video directory.
    After accept, read ``selected_csv_uri`` and ``selected_video_prefix``.
 
    In both modes, ``selected_profile`` returns the chosen AWS profile.
 
    Usage::
 
        # Video mode
        dlg = S3BrowserDialog(profiles, S3BrowserMode.VIDEO, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            uri = dlg.selected_video_uri
 
        # Session mode
        dlg = S3BrowserDialog(profiles, S3BrowserMode.SESSION, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            csv = dlg.selected_csv_uri
            pfx = dlg.selected_video_prefix
    """

    def __init__(
            self,
            profiles: list[str],
            mode: S3BrowserMode,
            parent=None
        ):
        super().__init__(parent)
        self._mode = mode
        self.setMinimumSize(600, 500)
        self.resize(750, 550)

        if mode == S3BrowserMode.VIDEO:
            self.setWindowTitle("Open Video from S3")
        else:
            self.setWindowTitle("Open Session from S3")

        # --- Internal state ---
        self._selected_csv_uri: str | None = None
        self._selected_video_prefix: str | None = None
        self._selected_video_uri: str | None = None
        self._selected_profile: str | None = None
        self._current_bucket: str = ""
        self._current_prefix: str = ""


        # --- LAYOUT ---
        layout = QVBoxLayout(self)

        # --- Connection settings ---
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout(conn_group)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("AWS Profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.addItems(profiles)
        if profiles:
            self._profile_combo.setCurrentIndex(0)
        profile_row.addWidget(self._profile_combo, stretch=1)
        conn_layout.addLayout(profile_row)

        bucket_row = QHBoxLayout()
        bucket_row.addWidget(QLabel("Bucket:"))
        self._bucket_input = QLineEdit()
        self._bucket_input.setPlaceholderText("my-video-bucket")
        self._bucket_input.returnPressed.connect(self._on_connect)
        bucket_row.addWidget(self._bucket_input, stretch=1)
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        bucket_row.addWidget(self._connect_btn)
        conn_layout.addLayout(bucket_row)

        layout.addWidget(conn_group)

        # --- File browaser ---
        browser_group = QGroupBox("Browser")
        browser_layout = QVBoxLayout(browser_group)

        nav_row = QHBoxLayout()
        self._up_btn = QPushButton("↑ Up")
        self._up_btn.setToolTip("Navigate to parent directory")
        self._up_btn.clicked.connect(self._on_navigate_up)
        self._up_btn.setEnabled(False)
        nav_row.addWidget(self._up_btn)

        self._path_label = QLabel("Not connected")
        self._path_label.setStyleSheet("color: #888;")
        nav_row.addWidget(self._path_label, stretch=1)
        browser_layout.addLayout(nav_row)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Size"])
        self._tree.setColumnWidth(0, 420)
        self._tree.setRootIsDecorated(False)
        self._tree.itemDoubleClicked.connect(
            self._on_item_double_clicked
        )
        self._tree.currentItemChanged.connect(
            self._on_selection_changed
        )
        browser_layout.addWidget(self._tree)

        layout.addWidget(browser_group, stretch=1)

        # --- Mode-specific selection panel ---
        if mode == S3BrowserMode.SESSION:
            self._build_session_panel(layout)
        else:
            self._build_video_panel(layout)

        # --- Cancel button ---
        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)

        # --- BACKGROUND WORKER ---
        self._worker = _S3ListWorker()
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._worker.listing_ready.connect(self._on_listing_ready)
        self._worker.error_occurred.connect(self._on_listing_error)
        self._thread.start()

    # --- MODE SPECIFIC PANEL BUILDERS ---
    def _build_session_panel(self, parent_layout: QVBoxLayout) -> None:
        """Build the CSV + video_dir selection panel for SESSION mode."""
        group = QGroupBox("Session Selection")
        group_layout = QVBoxLayout(group)

        # CSV row
        csv_row = QHBoxLayout()
        csv_row.addWidget(QLabel("CSV:"))
        self._csv_label = QLabel("(none — select a .csv file above)")
        self._csv_label.setStyleSheet("color: #aaa;")
        csv_row.addWidget(self._csv_label, stretch=1)
        self._set_csv_btn = QPushButton("Set Selected as CSV")
        self._set_csv_btn.setToolTip(
            "Use the highlighted .csv file in the browser"
        )
        self._set_csv_btn.clicked.connect(self._on_set_csv)
        self._set_csv_btn.setEnabled(False)
        csv_row.addWidget(self._set_csv_btn)
        group_layout.addLayout(csv_row)

        # Video directory row
        vdir_row = QHBoxLayout()
        vdir_row.addWidget(QLabel("Video Dir:"))
        self._video_dir_label = QLabel(
            "(none — navigate to the video folder above)"
        )
        self._video_dir_label.setStyleSheet("color: #aaa;")
        vdir_row.addWidget(self._video_dir_label, stretch=1)
        self._set_vdir_btn = QPushButton("Set Current as Video Dir")
        self._set_vdir_btn.setToolTip(
            "Use the directory currently shown in the browser"
        )
        self._set_vdir_btn.clicked.connect(self._on_set_video_dir)
        self._set_vdir_btn.setEnabled(False)
        vdir_row.addWidget(self._set_vdir_btn)
        group_layout.addLayout(vdir_row)

        # Accept button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._accept_btn = QPushButton("Open Session")
        self._accept_btn.setEnabled(False)
        self._accept_btn.setStyleSheet(
            "QPushButton { background-color: #2d7a4d; color: white; "
            "padding: 8px 20px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:disabled { background-color: #3a3a3a; "
            "color: #777; }"
            "QPushButton:hover { background-color: #359a5d; }"
        )
        self._accept_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._accept_btn)
        group_layout.addLayout(btn_row)
 
        parent_layout.addWidget(group)

    def _build_video_panel(self, parent_layout: QVBoxLayout) -> None:
        """Build the single-video selection panel for VIDEO mode."""
        group = QGroupBox("Video Selection")
        video_row = QHBoxLayout(group)
 
        self._video_file_label = QLabel(
            "Select a video file in the browser above"
        )
        self._video_file_label.setStyleSheet("color: #aaa;")
        video_row.addWidget(self._video_file_label, stretch=1)
 
        self._accept_btn = QPushButton("Open Video")
        self._accept_btn.setEnabled(False)
        self._accept_btn.setStyleSheet(
            "QPushButton { background-color: #2d6da8; color: white; "
            "padding: 8px 20px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:disabled { background-color: #3a3a3a; "
            "color: #777; }"
            "QPushButton:hover { background-color: #3d8dc8; }"
        )
        self._accept_btn.clicked.connect(self._on_accept)
        video_row.addWidget(self._accept_btn)
 
        parent_layout.addWidget(group)


    # --- CONNECTION ---
    def _on_connect(self) -> None:
        """Connect to the specified bucket and list its root."""
        bucket = self._bucket_input.text().strip()
        if not bucket:
            QMessageBox.warning(
                self, "No Bucket",
                "Please enter a bucket name."
            )
            return

        self._current_bucket = bucket
        self._current_prefix = ""
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting…")
        self._refresh_listing()


    # --- NAVIGATION ---

    def _refresh_listing(self) -> None:
        """Request a listing of the current prefix from the worker."""
        self._tree.clear()
        loading = QTreeWidgetItem(["Loading…"])
        loading.setFlags(Qt.ItemFlag.NoItemFlags)
        self._tree.addTopLevelItem(loading)
 
        self._worker.list_prefix(
            self._current_bucket,
            self._current_prefix,
            self._profile_combo.currentText(),
        )

    def _on_listing_ready(self, prefix: str, items: list) -> None:
        """Populate the tree with S3 listing results."""
        # Ignore stale responses from a previous navigation
        if prefix != self._current_prefix:
            return
        
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("Connect")

        self._tree.clear()
        self._path_label.setText(
            f"s3://{self._current_bucket}/{self._current_prefix}"
        )
        self._path_label.setStyleSheet("")
        self._up_btn.setEnabled(bool(self._current_prefix))

        # Enable the session mode buttons now that we're connected
        if self._mode == S3BrowserMode.SESSION:
            self._set_vdir_btn.setEnabled(True)
            self._set_csv_btn.setEnabled(True)

        if not items:
            empty = QTreeWidgetItem(["(empty directory)"])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._tree.addTopLevelItem(empty)
            return

        for item in items:
            size_text = (
                self._format_size(item.get("size", 0))
                if not item["is_prefix"] else ""
            )

            node = QTreeWidgetItem([
                item["display"],
                size_text
            ])
            node.setData(0, Qt.ItemDataRole.UserRole, item)
            
            if item["is_prefix"]:
                node.setIcon(0, self.style().standardIcon(
                    QStyle.StandardPixmap.SP_DirIcon
                ))
            
            self._tree.addTopLevelItem(node)

    def _on_listing_error(self, error: str) -> None:
        """Handle an error from the S3 listing worker."""
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("Connect")
        self._tree.clear()
 
        if self._mode == S3BrowserMode.SESSION:
            self._set_vdir_btn.setEnabled(False)
            self._set_csv_btn.setEnabled(False)
 
        QMessageBox.warning(
            self,
            "S3 Error",
            f"Failed to list bucket contents:\n\n{error}\n\n"
            f"Check that:\n"
            f"  • The bucket name is correct\n"
            f"  • Your AWS profile is valid\n"
            f"  • You have run 'aws sso login' if using SSO",
        )

    def _on_item_double_clicked(self, item, column) -> None:
        """Navigate into a directory on double-click."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data["is_prefix"]:
            self._current_prefix = data["key"]
            self._refresh_listing()

    def _on_navigate_up(self) -> None:
        """Navigate to the parent prefix."""
        if not self._current_prefix:
            return
        parts = self._current_prefix.rstrip("/").rsplit("/", 1)
        self._current_prefix = (parts[0] + "/") if len(parts) > 1 else ""
        self._refresh_listing()

    def _on_selection_changed(self, current, previous) -> None:
        """
        React to the user selecting a different item in the tree.

        In VIDEO mode: enable/disable the accept button based on whether the
        selected item is a recognised video file.

        In SESSION mode: no action needed - selection is committed explicitly
        via the 'Set selected as CSV' button
        """
        if self._mode == S3BrowserMode.VIDEO:
            self._update_video_selection(current)

    def _update_video_selection(self, current) -> None:
        """Update the video panel based on the current tree selection."""
        if current is None:
            self._accept_btn.setEnabled(False)
            self._video_file_label.setText(
                "Select a video file in the browser above"
            )
            self._video_file_label.setStyleSheet("color: #aaa;")
            self._selected_video_uri = None
            return
        
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if data is None or data["is_prefix"]:
            self._accept_btn.setEnabled(False)
            self._video_file_label.setText(
                "Select a video file in the browser above"
            )
            self._video_file_label.setStyleSheet("color: #aaa;")
            self._selected_video_uri = None
            return
        
        suffix = PurePosixPath(data["display"].lower()).suffix
        if suffix in _VIDEO_EXTENSIONS:
            uri = f"s3://{self._current_bucket}/{data['key']}"
            self._accept_btn.setEnabled(True)
            self._video_file_label.setText(data["display"])
            self._video_file_label.setStyleSheet("")
            self._selected_video_uri = uri
        else:
            self._accept_btn.setEnabled(False)
            self._video_file_label.setText(
                f"'{data['display']}' is not a recognised video format."
            )
            self._video_file_label.setStyleSheet("color: #aaa;")
            self._selected_video_uri = None

    
    # --- SESSION-MODEL SELECTION ---
    def _on_set_csv(self) -> None:
        """Set the currently selected tree item as the CSV file."""
        current = self._tree.currentItem()
        if current is None:
            QMessageBox.information(
                self, "No selection",
                "Select a .csv file in the browser first."
            )
            return
        
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if data is None or data["is_prefix"]:
            QMessageBox.information(
                self, "Select a File",
                "Please select a .csv file, not a directory."
            )
            return
        
        if not data["display"].lower().endswith(".csv"):
            QMessageBox.information(
                self, "Not a CSV",
                f"'{data['display']}' does not appear to be a CSV "
                f"file.\n\nPlease select a file ending in .csv.",
            )
            return
        
        uri = f"s3://{self._current_bucket}/{data['key']}"
        self._selected_csv_uri = uri
        self._csv_label.setText(uri)
        self._csv_label.setStyleSheet(
            "color: #2d7a4d; font-weight: bold;"
        )
        self._update_session_accept()

    def _on_set_video_dir(self) -> None:
        """Set the current browser prefix as the video directory."""
        uri = f"s3://{self._current_bucket}/{self._current_prefix}"
        self._selected_video_prefix = uri
        self._video_dir_label.setText(uri)
        self._video_dir_label.setStyleSheet(
            "color: #2d7a4d; font-weight: bold;"
        )
        self._update_session_accept()

    def _update_session_accept(self) -> None:
        """Enable the session accept button when both field are set."""
        self._accept_btn.setEnabled(
            self._selected_csv_uri is not None
            and self._selected_video_prefix is not None
        )

    
    # --- ACCEPT ---
    def _on_accept(self) -> None:
        """
        Accept the dialog.

        In VIDEO mode, validates that a video is selected.
        In SESSION mode, alidates that both CSV and video dir are set.
        (The accept button is already disabled when invalid, so this is a
        safety net.)
        """
        if self._mode == S3BrowserMode.VIDEO:
            if self._selected_video_uri is None:
                return
        else:
            if (self._selected_csv_uri is None 
                    or self._selected_video_prefix is None):
                return
            
        self._selected_profile = self._profile_combo.currentText()
        self.accept()


    # --- PUBLIC PROPERTIES ---
    @property
    def selected_csv_uri(self) -> str | None:
        """S3 URI of the selected CSV (SESSION mode only)."""
        return self._selected_csv_uri

    @property
    def selected_video_prefix(self) -> str | None:
        """S3 URI prefix for the video directory (SESSION mode only)."""
        return self._selected_video_prefix
    
    @property
    def selected_video_uri(self) -> str | None:
        """S3 URI of the selected video file (VIDEO mode only)."""
        return self._selected_video_uri

    @property
    def selected_profile(self) -> str | None:
        """The AWS profile name that was selected."""
        return self._selected_profile

    # --- HELPERS ---
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format a byte count as a human-readable string."""
        if size_bytes == 0:
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def closeEvent(self, event) -> None:
        """Shut down the background thread on close."""
        self._thread.quit()
        self._thread.wait()
        super().closeEvent(event)
