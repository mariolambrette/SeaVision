"""
Interactive detection bounding box for the QGraphcsScene in the SeaVision
validation GUI.

Provides a draggable, resizeable rectangle that represents a single detection
overlay on the video frame. Emits geometry changes through a callback so the
validation model can be updated.
"""

import logging
from enum import Enum, auto

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QCursor, QPainter
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QGraphicsSceneHoverEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

logger = logging.getLogger(__name__)

# Size of the resize handles in scene pixels. This is intentionally large - on a
# 640x480 display displayed at 2x, each handle is about 8 physical pixels, which
# is comformtable to grab with a mouse.
_HANDLE_SIZE = 3.0

# Minimum size of the box in frame pixels. Prevents the box from collapsing to zero or inverting
MIN_SIZE = 3.0


class _HandlePosition(Enum):
    """Which edge or corner a resize handle sits on."""
    TOP_LEFT = auto()
    TOP = auto()
    TOP_RIGHT = auto()
    RIGHT = auto()
    BOTTOM_RIGHT = auto()
    BOTTOM = auto()
    BOTTOM_LEFT = auto()
    LEFT = auto()


# Map each handle to the cursor shape shown when hovering above it
_HANDLE_CURSORS = {
    _HandlePosition.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
    _HandlePosition.TOP: Qt.CursorShape.SizeVerCursor,
    _HandlePosition.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
    _HandlePosition.RIGHT: Qt.CursorShape.SizeHorCursor,
    _HandlePosition.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
    _HandlePosition.BOTTOM: Qt.CursorShape.SizeVerCursor,
    _HandlePosition.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
    _HandlePosition.LEFT: Qt.CursorShape.SizeHorCursor,
}


class DetectionRectItem(QGraphicsRectItem):
    """
    An interactive bounding box for a single detection.

    Supports:
    - Click to select
    - Drag to move
    - Drag edges/corner handles to resize
    - Cursor changes to indicate available interaction
    - Geometry change callback for model updates

    The item operates in frame pixel coordinates - its rect() and pos() values
    correspond directly to pixel positions in the original video frame. The
    QGraphicsView handles the scaling between frame coordinates and screen
    pixels.

    Args:
        x: Left edge in frame pixels
        y: Top edge in frame pixels
        width: Width in frame pixels
        height: Height in frame pixels
        detection_id: The unique ID from ValidationModel, used to route geometry
            changes back to the correct detection.
        colour: BGR tuple for the box outline (converted to RGB internally).
        on_geometry_changed: Callback invoked when the user finishes dragging.
            Receives (detection_id, xc, yc, width, height) in frame coordinates
            using centre-format to match the Detection dataclass convention.
        parent: Optional parent QGraphicsItem.
    """

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        detection_id: int,
        colour: tuple[int, int, int] = (0, 0, 255),
        on_geometry_changed: callable = None,
        parent: QGraphicsItem | None = None,
    ):
        
        super().__init__(x, y, width, height, parent)

        self._detection_id = detection_id
        self._on_geometry_changed = on_geometry_changed

        # --- Interaction flags ---
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True
        )
        self.setAcceptHoverEvents(True)

        # --- Visual style ---
        # COnvert BGR (OpenCV format) to RGB (Qt format)
        b, g, r = colour
        pen_colour = QColor(r, g, b)
        pen = QPen(pen_colour, 2.0)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self._default_pen_colour = pen_colour

        # --- Resize state ---
        self._active_handle: _HandlePosition | None = None
        self._drag_start_rect: QRectF | None = None
        self._drag_start_pos: QPointF | None = None

        # --- Frame bounds (set externally to clamp movement) ---
        self._frame_width: float = 0.0
        self._frame_height: float = 0.0

    def set_frame_bounds(self, width: float, height: float) -> None:
        """
        Set the frame dimensions for clamping box movement.

        Called once when the item is created. Prevents the reviewer from
        dragging a box outside the visible frame area.
        """
        self._frame_width = width
        self._frame_height = height

    @property
    def detection_id(self) -> int:
        """The unique ID of the detection this box represents."""
        return self._detection_id
    
    def _current_handle_size(self) -> float:
        """
        Compute handle size in scene coordinates that maps to a consistent
        screen size.

        If no view is available (item not in a scene yet), falls back to
        the default.
        """
        if self.scene() is None:
            return _HANDLE_SIZE

        views = self.scene().views()
        if not views:
            return _HANDLE_SIZE

        # Get the view's horizontal scale factor
        transform = views[0].transform()
        scale = transform.m11()  # horizontal scale

        if scale <= 0:
            return _HANDLE_SIZE

        # Target: 5 screen pixels per handle half-size
        return 6.0 / scale
    
    def _handle_rects(self) -> dict[_HandlePosition, QRectF]:
        """
        Calculates the rectangles for all eight resize handles.

        Handles are positioned at the four corners and the midpoints of the
        four edges, each centered on the edge/corner point with a size of
        _HANDLE_SIZE in each direction.

        Returns coordinates in the item's local coordinate system.
        """
        r = self.rect()
        s = self._current_handle_size()
        cx = r.x() + r.width() / 2
        cy = r.y() + r.height() / 2

        return {
            _HandlePosition.TOP_LEFT: QRectF(
                r.x() - s, r.y() - s, 2 * s, 2 * s
            ),
            _HandlePosition.TOP: QRectF(
                cx - s, r.y() - s, 2 * s, 2 * s
            ),
            _HandlePosition.TOP_RIGHT: QRectF(
                r.right() - s, r.y() - s, 2 * s, 2 * s
            ),
            _HandlePosition.RIGHT: QRectF(
                r.right() - s, cy - s, 2 * s, 2 * s
            ),
            _HandlePosition.BOTTOM_RIGHT: QRectF(
                r.right() - s, r.bottom() - s, 2 * s, 2 * s
            ),
            _HandlePosition.BOTTOM: QRectF(
                cx - s, r.bottom() - s, 2 * s, 2 * s
            ),
            _HandlePosition.BOTTOM_LEFT: QRectF(
                r.x() - s, r.bottom() - s, 2 * s, 2 * s
            ),
            _HandlePosition.LEFT: QRectF(
                r.x() - s, cy - s, 2 * s, 2 * s
            ),
        }
    
    def _handle_at(self, pos: QPointF) -> _HandlePosition | None:
        """
        Determine which handle (if any) is under the given local position.

        Returns None if the position is inside the rect but not on a handle,
        meaning a drag should move the whole box rather than resize it.
        """
        for handle, rect in self._handle_rects().items():
            if rect.contains(pos):
                return handle
        return None
    

    # --- Hover events (cursor feedback) ---
    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
        """Change cursor based on which handle the mouse is near."""
        handle = self._handle_at(event.pos())
        if handle is not None:
            self.setCursor(QCursor(_HANDLE_CURSORS[handle]))
        else:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """reset cursor when the mouse leaves the item."""
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))


    # --- Mouse events (drag and resize) ---
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """
        Start a drag operation.

        If the press is on a handle, begin resizing. Otherwise, begin moving
        the whole box (handled by Qt's built-in ItemIsMovable)
        """

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        
        self._active_handle = self._handle_at(event.pos())

        if self._active_handle is not None:
            # Resize - record the starting geometry to compute delatas during
            # mouseMoveEvent.
            self._drag_start_rect = QRectF(self.rect())
            self._drag_start_pos = event.pos()

            # Disable movement during the drag
            self.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False
            )
            event.accept()
        else:
            # Normal move - let Qt handle it vaia ItemIsMovable
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handle a drag movement.

        During resize: compute the new rect from the mouse delta and the active
        handle.
        During move: delegate to Qt's built in handling.
        """
        if self._active_handle is not None and self._drag_start_rect is not None:
            self.resize_to(event.pos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Finish a drag operation and notify the model.

        Re-enables ItemIsMovable (which was disbaled during resize) and fires
        the geometry changed callback with the new coordinates.
        """
        was_resizing = self._active_handle is not None

        self._active_handle = None
        self._drag_start_rect = None
        self._drag_start_pos = None

        # Re-enable movement for future drags
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True
        )

        super().mouseReleaseEvent(event)
        self._notify_geometry_changed()

    def resize_to(self, current_pos: QPointF) -> None:
        """
        Update the rectangle during a resize drag.

        Computes the new rect by adjusting the edge(s) corresponding to the
        active handle by the mouse delta since the drag started.
        Enforces a minimum size to prevent the box from collapsing to 0 or
        inverting.
        """
        if self._drag_start_rect is None or self._drag_start_pos is None:
            return
        
        self.prepareGeometryChange()

        dx = current_pos.x() - self._drag_start_pos.x()
        dy = current_pos.y() - self._drag_start_pos.y()

        r = QRectF(self._drag_start_rect)
        handle = self._active_handle

        # Adjust the appropiate edges based on which handle is active
        if handle in (
            _HandlePosition.TOP_LEFT,
            _HandlePosition.TOP,
            _HandlePosition.TOP_RIGHT,
        ):
            new_top = r.top() + dy
            if r.bottom() - new_top >= MIN_SIZE:
                r.setTop(new_top)

        if handle in (
            _HandlePosition.BOTTOM_LEFT,
            _HandlePosition.BOTTOM,
            _HandlePosition.BOTTOM_RIGHT,
        ):
            new_bottom = r.bottom() + dy
            if new_bottom - r.top() >= MIN_SIZE:
                r.setBottom(new_bottom)

        if handle in (
            _HandlePosition.TOP_LEFT,
            _HandlePosition.LEFT,
            _HandlePosition.BOTTOM_LEFT,
        ):
            new_left = r.left() + dx
            if r.right() - new_left >= MIN_SIZE:
                r.setLeft(new_left)

        if handle in (
            _HandlePosition.TOP_RIGHT,
            _HandlePosition.RIGHT,
            _HandlePosition.BOTTOM_RIGHT,
        ):
            new_right = r.right() + dx
            if new_right - r.left() >= MIN_SIZE:
                r.setRight(new_right)

        self.setRect(r)

    def _notify_geometry_changed(self) -> None:
        """
        Convert the current item geometry to centre-format and invoke the
        callback.

        The callback signature matches ValidationModel.set_corrected_geometry:
        (detection_id, xc, yc, width, height) - all in frame pixel coordinates.
        """
        if self._on_geometry_changed is None:
            return
        
        # The item's scene position plus its local rect give the absolute frame
        # coordinates. Since we set items at pos (0, 0) and use the rect for
        # positioning, the rect coordinates ARE the frame coordinates.
        r = self.rect()
        pos = self.pos()

        # Absolute frame coordinaates
        abs_x = pos.x() + r.x()
        abs_y = pos.y() + r.y()
        w = r.width()
        h = r.height()

        # Convert corner-format to centre-format
        xc = abs_x + w / 2
        yc = abs_y + h / 2

        self._on_geometry_changed(
            self._detection_id, xc, yc, w, h
        )

    def boundingRect(self) -> QRectF:
        """
        Expand the bounding rect to include resize handles.
        
        QGraphicsScene uses the bounding rect for hit testing and repaint
        scheduling. If we don;t expand it, the handles (which extend beyond the
        rectangles edges) won't recieve mouse events and won't be repainted
        correctly.
        """
        r = self.rect()
        margin = self._current_handle_size() + 1
        return r.adjusted(-margin, -margin, margin, margin)
    
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """
        Draw the bounding box and, if selected, the resize handles.

        The base rectangle is always drawn. When selected, the box colour
        changes to cyan and resize handles appear at corners and edge
        midpoints.
        """

        # Use cyan pen when selected, default pen otherwise
        if self.isSelected():
            highlight_pen = QPen(QColor(0, 255, 255), 2.0)
            highlight_pen.setCosmetic(True)
            painter.setPen(highlight_pen)
        else:
            painter.setPen(self.pen())

        painter.setBrush(self.brush())
        painter.drawRect(self.rect())

        # Draw resize handles when selected
        if self.isSelected():
            handle_pen = QPen(QColor(255, 255, 255), 1.0)
            handle_pen.setCosmetic(True)
            handle_brush = QBrush(QColor(0, 255, 255))
            painter.setPen(handle_pen)
            painter.setBrush(handle_brush)

            for rect in self._handle_rects().values():
                painter.drawRect(rect)

    def itemChange(self, change, value):
        """
        Clamp the item position to stay within frame bounds.

        Called by Qt whenever the item's position changes (because we set the
        ItemSendsGeometryChanges flag). We intercept position changes and adjust
        them to keep the box within the frame.
        """
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self._frame_width > 0
            and self._frame_height > 0
        ):
            r = self.rect()
            new_pos = QPointF(value)

            # Clamp so the box stays within frame bounds
            min_x = -r.x()
            min_y = -r.y()
            max_x = self._frame_width - r.x() - r.width()
            max_y = self._frame_height - r.y() - r.height()

            new_pos.setX(max(min_x, min(new_pos.x(), max_x)))
            new_pos.setY(max(min_y, min(new_pos.y(), max_y)))

            return new_pos
        
        return super().itemChange(change, value)
    
    def update_colour(self, bgr: tuple[int, int, int]) -> None:
        """Update the box colour (e.g. after status change)."""
        b, g, r = bgr
        colour = QColor(r, g, b)
        pen = QPen(colour, 2.0)
        pen.setCosmetic(True)
        self.setPen(pen)
        self._default_pen_colour = colour
        self.update()
