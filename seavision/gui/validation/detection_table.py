"""Detection table model and view for the validation workflow."""

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    Signal,
    QSortFilterProxyModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableView,
)

from seavision.engine.detectors.base import Detection

# Column definitions: (display_name, attribute_or_key, width_hint)
COLUMNS = [
    ("Frame", "frame_number", 60),
    ("Time", "time", 70),
    ("Confidence", "confidence", 80),
    ("Label", "label", 80),
    ("Track", "track_id", 50),
]


class DetectionTableModel(QAbstractTableModel):
    """
    Table model backed by a list of detection objects.

    Implements the required QAbstractTableModel interface so that any
    QTableView can display detection data. The model is read-only for now - 
    development phase 4 will add the mutable Status column.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._detections: list = []
        self._fps: float | None = None

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
        
        detection = self._detections[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(detection, col)
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            # Centre align numeric columns (frame, Time, Confidence, Track)
            if col in (0, 1, 2, 4):
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


        
        return None
    
    # --- Value display helper ---
    def _display_value(self, detection: Detection, col: int) -> str:
        """
        Format a detection field for display.
        """
        if col == 0: # Frame
            return str(detection.frame_number)
        
        if col == 1:  # Time
            if self._fps is not None and self._fps > 0:
                timestamp = detection.frame_number / self._fps if self._fps > 0 else 0.0
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
            detections: list[Detection],
            fps: float | None = None,
    ) -> None:
        """
        Replace the detection list and refresh all connected views.

        Args:
            detections: New list of detection objects.
            fps: Video frame rate, used for timestamp calculation.
        """
        self.beginResetModel()
        self._detections = list(detections)
        self._fps = fps
        self.endResetModel()

    # --- Accessory methods ---
    def detection_at(self, row: int) -> Detection | None:
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
        seen = sorted(set(d.frame_number for d in self._detections))
        return seen


class DetectionTableView(QTableView):
    """
    Table view for displaying detections with click-to-select.
    
    Emits detection_selected when the user clixks a row. The signal carries both
    row index (for looking up the Detection from the model) and the frame number
    (for seeking the video).
    """

    detection_selected = Signal(int, int) # row index, frame number

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proxy: QSortFilterProxyModel | None = None
        self._setup_appearance()

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

    def setModel(self, model: DetectionTableModel) -> None:
        """
        Set the model and connect selection handling.

        Also applies the colum width hints from the COLUMNS definition.
        """
        self._proxy = QSortFilterProxyModel(self)
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
        
        detection = model.detection_at(row)
        if detection is not None:
            self.detection_selected.emit(row, detection.frame_number)

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
            self.scrollTo(proxy_index)
