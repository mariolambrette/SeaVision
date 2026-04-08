"""Detection table model and view for the validation workflow."""

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    Signal,
    QSortFilterProxyModel,
)
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableView,
)

from seavision.engine.detectors.base import Detection
from seavision.gui.validation.validation_model import (
    ValidatedDetection,
    ValidationStatus,
)

# Column definitions: (display_name, attribute_or_key, width_hint)
COLUMNS = [
    ("Frame", "frame_number", 60),
    ("Time", "time", 70),
    ("Confidence", "confidence", 80),
    ("Label", "label", 80),
    ("Track", "track_id", 50),
    ("Status", "status", 60),
]

_STATUS_SYMBOLS = {
    ValidationStatus.PENDING: "·",
    ValidationStatus.CONFIRMED: "✓",
    ValidationStatus.REJECTED: "✗",
    ValidationStatus.SKIPPED: "—",
    ValidationStatus.CORRECTED: "✎",
}

# --- Status colours ---
_STATUS_FOREGROUND = {
    ValidationStatus.CONFIRMED: QBrush(QColor("#2d8a4e")),   # green
    ValidationStatus.REJECTED: QBrush(QColor("#c0392b")),    # red
    ValidationStatus.SKIPPED: QBrush(QColor("#888888")),     # grey
    ValidationStatus.CORRECTED: QBrush(QColor("#2d6da8")),   # blue
    # PENDING: return None (default text colour)
}

_STATUS_BACKGROUND = {
    ValidationStatus.CONFIRMED: QBrush(QColor(45, 138, 78, 25)),   # light green
    ValidationStatus.REJECTED: QBrush(QColor(192, 57, 43, 25)),    # light red
    # PENDING, SKIPPED, CORRECTED: return None (no background)
}

class DetectionTableModel(QAbstractTableModel):
    """
    Table model backed by a list of detection objects.

    Implements the required QAbstractTableModel interface so that any
    QTableView can display detection data. The model is read-only for now - 
    development phase 4 will add the mutable Status column.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._detections: list[ValidatedDetection] = []
        self._fps: float | None = None
        self._selected_id: int | None = None

    # --- Compulsory interface methods ---
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Number of detections in the table."""
        return len(self._detections)
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Number of columns in the table."""
        return len(COLUMNS)
    
    # --- Main column display logic ---
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """
        Return data for a cell.

        The view calls this for every visible cell with different roles:
        - DisplayRole: the text to show
        - TextAlignmentRole: how to align the text
        - Other roles: return None to use the view's defaults
        """
        if not index.isValid() or index.row() >= len(self._detections):
            return None
        
        vd = self._detections[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(vd, col)
        
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 5:
                return _STATUS_FOREGROUND.get(vd.status)
            return None
        
        if role == Qt.ItemDataRole.BackgroundRole:
            return _STATUS_BACKGROUND.get(vd.status)
        
        if role == Qt.ItemDataRole.FontRole:
            font = QFont()
            changed = False

            if vd.is_manual:
                font.setItalic(True)
                changed = True

            if self._selected_id is not None and vd.id == self._selected_id:
                font.setBold(True)
                changed = True

            if col == 5:  # Status column — slightly larger
                font.setPointSize(font.pointSize() + 2)
                changed = True

            return font if changed else None
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            # Centre align numeric columns (frame, Time, Confidence, Track)
            if col in (0, 1, 2, 4):
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            
        return None
    
    def set_selected_id(self, detection_id: int | None) -> None:
        """
        Mark a detection as selected so its row renders in bold.

        Emits dataChanged for both the previously selected row and the
        newly selected row so their FontRole is re-queried.
        """
        old_id = self._selected_id
        self._selected_id = detection_id

        # Repaint the old row (un-bold it)
        if old_id is not None:
            for row, vd in enumerate(self._detections):
                if vd.id == old_id:
                    self.dataChanged.emit(
                        self.index(row, 0),
                        self.index(row, self.columnCount() - 1),
                    )
                    break

        # Repaint the new row (bold it)
        if detection_id is not None:
            for row, vd in enumerate(self._detections):
                if vd.id == detection_id:
                    self.dataChanged.emit(
                        self.index(row, 0),
                        self.index(row, self.columnCount() - 1),
                    )
                    break

    # --- Value display helper ---
    def _display_value(
        self, validated_det: ValidatedDetection, col: int
    ) -> str:
        """
        Format a detection field for display.

        Args:
            validaed_det: The ValidatedDetection wrapping the raw Detection.
            col: Column index.
        """
        detection = validated_det.detection

        if col == 0: # Frame
            return str(detection.frame_number)
        
        if col == 1:  # Time
            if self._fps is not None and self._fps > 0:
                timestamp = detection.frame_number / self._fps
                mins = int(timestamp // 60)
                secs = timestamp % 60
                return f"{mins}:{secs:04.1f}"
            return "—"
        
        if col == 2: # Confidence
            if detection.confidence is not None:
                return f"{detection.confidence:.2f}"
            else:
                return "—"
        
        if col == 3: # Label
            return detection.label if detection.label else "—"
        
        if col == 4: # Track
            if detection.track_id is not None:
                return str(detection.track_id)
            else:
                return "—"

        if col == 5: # Status
            return _STATUS_SYMBOLS.get(validated_det.status, "·")
            
        return ""
    
    # --- Column header display ---
    def headerData(
        self, 
        section: int, # Column index for horizontal headers
        orientation: Qt.Orientation, 
        role: int = Qt.ItemDataRole.DisplayRole
    ):
        """Return column header labels."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(COLUMNS):
                return COLUMNS[section][0]
        return None
        

    # --- Set detection ---
    def set_detections(
            self,
            detections: list[ValidatedDetection],
            fps: float | None = None,
    ) -> None:
        """
        Replace the detection list and refresh all connected views.

        Args:
            detections: New list of ValidatedDetection objects.
            fps: Video frame rate, used for timestamp calculation. None if
                unkown
        """
        self.beginResetModel()
        self._detections = list(detections)
        self._fps = fps
        self.endResetModel()

    
    # --- Add/remove manual detections ---
    def append_detection(self, vd: ValidatedDetection) -> None:
        """
        Add a single detection to the end of the table.

        Uses beginInsertRows/endInsertRows for a surgical updated - the view
        inserts one row without losing selection or scroll position
        """

        row = len(self._detections)
        self.beginInsertRows(self.index(0, 0).parent(), row, row)
        self._detections.append(vd)
        self.endInsertRows()

    def remove_detection_by_id(self, detection_id: int) -> None:
        """
        Remove a detection by its unique ID.

        Uses beginRemoveRows/endRemoveRows for a surgical update. Does nothing
        if the ID is not found in the current list.
        """
        for row, vd in enumerate(self._detections):
            if vd.id == detection_id:
                self.beginRemoveRows(
                    self.index(0, 0).parent(), row, row
                )
                self._detections.pop(row)
                self.endRemoveRows()
                return

    # --- Accessory methods ---
    def detection_at(self, row: int) -> ValidatedDetection | None:
        """Return the Detection object at the given row index."""
        if 0 <= row < len(self._detections):
            return self._detections[row]
        return None
    
    def detection_count(self) -> int:
        """Return the total number of detections in the model."""
        return len(self._detections)
    
    def frame_numbers_sorted(self) -> list[int]:
        """
        Sorted list of unique frame numbers with detections.

        Used by the navigation logic to find previous/next detection frames with
        bisect (In ValidationTab).
        """
        seen = sorted(set(
            d.detection.frame_number for d in self._detections
        ))
        return seen


class DetectionFilterProxy(QSortFilterProxyModel):
    """
    Proxy model that filters detections by ValidationStatus or origin.

    Set the filter with set_status_filter(). Pass None to show all detections.
    Use set_manual_filter(True) to show onlymanually added detections.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status_filter: ValidationStatus | None = None
        self._manual_only: bool = False
        self._class_filter: str | None = None

    def sourceModel(self) -> DetectionTableModel | None:
        """Return the source model wiht correct type."""
        model = super().sourceModel()
        if isinstance(model, DetectionTableModel):
            return model
        return None

    def set_status_filter(
        self, status: ValidationStatus | None
    ) -> None:
        """
        Set which status to show. None means show all detections. Triggers an
        immediate re-filter.
        """
        self._status_filter = status
        self._manual_only = False
        self.invalidateFilter()

    def set_manual_filter(self, enabled: bool) -> None:
        """Show only manually added detections."""
        self._manual_only = enabled
        if enabled:
            self._status_filter = None
        self.invalidateFilter()

    def set_class_filter(self, class_name: str | None) -> None:
        """Show only detections of a certain class."""
        self._class_filter = class_name
        self.invalidateFilter()

    def filterAcceptsRow(
        self, source_row: int, source_parent
    ) -> bool:
        """
        Return True is this row should be visible.

        If no filter is set, all rows pass. Otherwise, only rows whose 
        ValidationStatus or origin matches the filter pass.
        """
        source_model = self.sourceModel()
        if source_model is None:
            return True

        vd = source_model.detection_at(source_row)
        if vd is None:
            return True

        # Class filter applies regardless of other filters
        if self._class_filter is not None:
            if vd.detection.label != self._class_filter:
                return False

        # Manual filter
        if self._manual_only:
            return vd.is_manual

        # Status filter
        if self._status_filter is not None:
            return vd.status == self._status_filter

        return True



class DetectionTableView(QTableView):
    """
    Table view for displaying detections with click-to-select.
    
    Emits detection_selected when the user clixks a row. The signal carries both
    row index (for looking up the Detection from the model) and the frame number
    (for seeking the video).
    """

    detection_selected = Signal(int, int) # row index, frame number
    context_action = Signal(str, int) # action_name, source_row

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proxy: DetectionFilterProxy | None = None
        self._setup_appearance()

        # --- Right click context menus ---
        self.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.customContextMenuRequested.connect(
            self._on_context_menu
        )

    def _setup_appearance(self) -> None:
        """Configure the table's visual behaiour."""
        # Selection behaviour: clicking selects the whole row
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        # Only one row can be selected at a time
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        # Subtle zebra striping for readability
        self.setAlternatingRowColors(True)

        # Column headers are clickable to sort
        self.setSortingEnabled(True)

        # Hide the vertical header (row numbers)
        self.verticalHeader().setVisible(False)

        # Last column stretches to fill remaining space
        self.horizontalHeader().setStretchLastSection(True)

        # Bold text for the selected row
        self.setStyleSheet("""
            QTableView::item:selected {
                font-weight: bold;
            }
        """)

    def setModel(self, model: DetectionTableModel) -> None:
        """
        Set the model and connect selection handling.

        Also applies the colum width hints from the COLUMNS definition.
        """
        self._proxy = DetectionFilterProxy(self)
        self._proxy.setSourceModel(model)
        
        super().setModel(self._proxy)

        # Apply column widths
        for i, (_, _, width) in enumerate(COLUMNS):
            self.setColumnWidth(i, width)

        # Connect selection changes
        self.selectionModel().currentRowChanged.connect(
            self._on_row_changed
        )

    def _on_row_changed(
            self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        """Handle a new row being selected in the table."""
        if not current.isValid():
            return
        
        # Map through the sort proxy to get the source model's row
        source_index = current
        if hasattr(current.model(), "mapToSource"):
            source_index = current.model().mapToSource(current)

        row = source_index.row()
        model = self._source_model()

        if model is None:
            return
        
        vd = model.detection_at(row)
        if vd is not None:
            self.detection_selected.emit(row, vd.detection.frame_number)

    def _source_model(self) -> DetectionTableModel | None:
        """Get the underlying DetectionTableModel, bypassing any proxy."""
        model = self.model()
        if model is None:
            return None
        
        # If sorting is enabled, Qt wraps in a QSortFilterProxyModel
        if hasattr(model, "sourceModel"):
            return model.sourceModel()
        return model
    
    def select_row(self, row: int) -> None:
        """
        Programmatically select a row in the table.

        Scrolls the table to make the row visible and triggers the selection
        signal.

        Args:
            row: Row index in the source model (not the proxy)
        """
        model = self.model()
        if model is None:
            return
        
        # If there's a sort proxy, map from source row to the proxy row index
        if hasattr(model, "mapFromSource"):
            source_model = model.sourceModel()
            source_index = source_model.index(row, 0)
            proxy_index = model.mapFromSource(source_index)
        else:
            proxy_index = model.index(row, 0)

        if proxy_index.isValid():
            self.setCurrentIndex(proxy_index)
            self.scrollTo(
                proxy_index
            )

    def _on_context_menu(self, pos) -> None:
        """Show a context menu for the right clicked row."""
        index = self.indexAt(pos)
        if not index.isValid():
            return
        
        # Map through the proxy to get the source row
        source_index = self._proxy.mapToSource(index)
        source_row = source_index.row()

        menu = QMenu(self)

        confirm = menu.addAction("Confirm")
        reject = menu.addAction("Reject")
        skip = menu.addAction("Skip")

        # Check if this is a manual detection
        model = self._proxy.sourceModel()

        vd = model.detection_at(source_row)
        remove = None
        undo_correction = None
        if vd and vd.is_manual:
            menu.addSeparator()
            remove = menu.addAction("Remove")

        menu.addSeparator()
        change_label = menu.addAction("Change Label")
        if vd and vd.corrected_geometry is not None:
            undo_correction = menu.addAction("Undo Correction")
        rename_label = menu.addAction("Rename Label")

        menu.addSeparator()
        select = menu.addAction("Select")

        action = menu.exec(self.viewport().mapToGlobal(pos))

        if action == confirm:
            self.context_action.emit("confirm", source_row)
        elif action == reject:
            self.context_action.emit("reject", source_row)
        elif action == skip:
            self.context_action.emit("skip", source_row)
        elif action is remove:
            self.context_action.emit("remove", source_row)
        elif action == select:
            self.context_action.emit("select", source_row)
        elif action == change_label:
            self.context_action.emit("change_label", source_row)
        elif action == rename_label:
            self.context_action.emit("rename_label", source_row)
        elif action == undo_correction:
            self.context_action.emit("undo_correction", source_row)
