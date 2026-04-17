"""
Graphics scene for interactive frame display with editable bounding boxes.

Manages the video frame pixmap and the set of DetectionRectItem overlays.
Provides methods to update the frame, synchronise detection overlays with the
ValidationModel, and handle draw-to-create for manual detections.
"""

import logging
from typing import Optional

from PySide6.QtCore import Signal, Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QImage, QPen, QColor, QBrush
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsSceneMouseEvent,
)

from seavision.gui.validation.detection_rect_item import (
    DetectionRectItem,
    MIN_SIZE
)

logger = logging.getLogger(__name__)


class InteractiveFrameScene(QGraphicsScene):
    """
    Scene containing a video frame pixmap and interactive detection overlays.

    Reponsibilities:
    - Display the current video frame as a background pixmap.
    - Create and amange DetectionRectItem instances for each visibile detection.
    - Handle the draw-to-create interaction for manual detection addition.
    - Emit signals when detections are modified or created.

    The scene operates in frame pixel coordinates. The top left corner of the
    frame is (0, 0) and the bottom right corner is (frame_width, frame_height).
    The QGraphicsView handles scaling these to screen pixels.

    Signals:
        detection_geometry_changed(int, float, float, float, float):
            Emitted when a detection box is dragged or resized.
            Args: detection_id, xc, yc, width, height (centre format, frame pixels)

        detection_draw_complete(float, float, float, float):
            Emitted when the user finishes drawing a new bounding box.
            Args: xc, yc, width, height (centre format, frame pixels)

        detection_rect_selected(int):
            Emitted when a detection rect is clicked in the scene.
            Args: detection_id
    """

    detection_geometry_changed = Signal(int, float, float, float, float)
    detection_draw_complete = Signal(float, float, float, float)
    detection_rect_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Frame pixmap ---
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._frame_width: int = 0
        self._frame_height: int = 0

        # --- Detection overlays ---
        # Map from detection_id to the rect item, for efficient lookup when we
        # need to update or remove a specific detection.
        self._detection_items: dict[int, DetectionRectItem] = {}

        # --- Draw-to-create state ---
        self._draw_mode: bool = False
        self._draw_origin: QPointF | None = None
        self._draw_rubber_band: DetectionRectItem | None = None

        # --- Highlighted detection ---
        self._highlighted_id: int | None = None

        # Scene background
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        # Selection handling
        self._setup_selection_handling()

    
    def update_frame(self, image: QImage) -> None:
        """
        Display a new video frame.

        Replaces the background pixmap. Does NOT clear detection overlays - 
        those are managed separately by set_detections() so they persist across
        frame updates during playback.
        """
        pixmap = QPixmap.fromImage(image)
        self._frame_width = pixmap.width()
        self._frame_height = pixmap.height()

        if self._pixmap_item is None:
            self._pixmap_item = self.addPixmap(pixmap)
            self._pixmap_item.setZValue(-1)  # Behind everything
            self.setSceneRect(0, 0, self._frame_width, self._frame_height)
        else:
            self._pixmap_item.setPixmap(pixmap)

            # Update scene rect if frame dimensions changed
            current = self.sceneRect()
            if (
                current.width() != self._frame_width
                or current.height() != self._frame_height
            ):
                self.setSceneRect(0, 0, self._frame_width, self._frame_height)

    def set_detections(
        self,
        detections: list[dict],
    ) -> None:
        """
        Synchronise detection overlays with the current state.

        Clears all existing detection items and creates new ones from the 
        provided list. Each dict must contain:
            detection_id (int), x1 (float), y1 (float),
            width (float), height (float),
            colour (tuple[int,int,int] — BGR),
            editable (bool)

        This is called whenever the frame changes (during seeking) or when
        a detection's status changes (needing a colour update).
        """
        self._clear_detection_items()

        for det_info in detections:
            item = DetectionRectItem(
                x=det_info["x1"],
                y=det_info["y1"],
                width=det_info["width"],
                height=det_info["height"],
                detection_id=det_info["detection_id"],
                colour=det_info["colour"],
                on_geometry_changed=self._on_item_geometry_changed,
            )
            item.set_frame_bounds(self._frame_width, self._frame_height)

            # Only allow editing on selected/editable detections
            if not det_info.get("editable", True):
                item.setFlag(
                    DetectionRectItem.GraphicsItemFlag.ItemIsMovable, False
                )
                item.setFlag(
                    DetectionRectItem.GraphicsItemFlag.ItemIsSelectable, False
                )
                item.setAcceptHoverEvents(False)

            self.addItem(item)
            self._detection_items[det_info["detection_id"]] = item

    def highlight_detection(self, detection_id: int | None) -> None:
        """
        Visually highlight a detection (e.g. the currently selected one).

        Selects the item in the scene's selection system, which triggers the
        resize handles to appear via DetectionRectItem.paint().
        """
        # Deselect previous
        if self._highlighted_id is not None:
            prev = self._detection_items.get(self._highlighted_id)
            if prev is not None:
                prev.setSelected(False)

        self._highlighted_id = detection_id

        if detection_id is not None:
            item = self._detection_items.get(detection_id)
            if item is not None:
                item.setSelected(True)

    def _clear_detection_items(self) -> None:
        """Remove all detection rect items from the scene."""
        for item in self._detection_items.values():
            self.removeItem(item)
        self._detection_items.clear()

    def _on_item_geometry_changed(
        self,
        detection_id: int,
        xc: float,
        yc: float,
        width: float,
        height: float,
    ) -> None:
        """
        Route a geometry change from a DetectionrectItem to the scene signal.

        This is callback passed to each item at contruction time. It just
        re-emits the change as a scene-level signal so the tab can pick it up.
        """
        self.detection_geometry_changed.emit(
            detection_id, xc, yc, width, height
        )


    # --- Draw-to-create mode ---
    def set_draw_mode(self, enabled: bool) -> None:
        """
        Toggle draw_to_create mode,

        When enable, clicking and draggin on th eframe creates a new bounding
        box. The rubber band rectangle follows the mouse during the grag. On
        release, detection_draw_complete is emitted with the drawn
        rectangle's coordinates.
        """
        self._draw_mode = enabled
        if not enabled and self._draw_rubber_band is not None:
            self.removeItem(self._draw_rubber_band)
            self._draw_rubber_band = None
            self._draw_origin = None

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handle mouse press - start drawing if in draw mode.

        In draw mode, we intercept the press to start the rubber band rectangle.
        Otherwise, we delegate to the base class so normal item selection and
        dragging work.
        """
        if (
            self._draw_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            pos = event.scenePos()

            # Only start drawing if the click is within the frame
            if (
                0 <= pos.x() <= self._frame_width
                and 0 <= pos.y() <= self._frame_height
            ):
                self._draw_origin = pos

                # Create a zero-size rect at the click point
                self._draw_rubber_band = DetectionRectItem(
                    x=pos.x(),
                    y=pos.y(),
                    width=0,
                    height=0,
                    detection_id=-1,  # Temporary ID for the rubber band
                    colour=(0, 200, 200),  # Cyan for drawing feedback
                    on_geometry_changed=None,  # No need to track geometry changes
                )

                # Disable interaction on the rubber band
                self._draw_rubber_band.setFlag(
                    DetectionRectItem.GraphicsItemFlag.ItemIsMovable, False
                )
                self._draw_rubber_band.setFlag(
                    DetectionRectItem.GraphicsItemFlag.ItemIsSelectable, False
                )
                self._draw_rubber_band.setAcceptHoverEvents(False)
                self.addItem(self._draw_rubber_band)
                event.accept()
                return
    
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Update the rubber band rectangle during draw-to-create drag."""
        if (
            self._draw_mode
            and self._draw_origin is not None
            and self._draw_rubber_band is not None
        ):
            pos = event.scenePos()

            # Clamp to frame bounds
            x = max(0, min(pos.x(), self._frame_width))
            y = max(0, min(pos.y(), self._frame_height))

            # Calculate the rect fromthe origin to current position, handling
            # any drag direction (top-left to bottom-right, bottom-right to 
            # top-left, etc.)
            x1 = min(self._draw_origin.x(), x)
            y1 = min(self._draw_origin.y(), y)
            x2 = max(self._draw_origin.x(), x)
            y2 = max(self._draw_origin.y(), y)

            self._draw_rubber_band.prepareGeometryChange()
            self._draw_rubber_band.setRect(QRectF(x1, y1, x2 - x1, y2 - y1))
            event.accept()
            return
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Finish drawing and emit the new detection's coordinates.

        Enforces a minimum size - very small accidental drags are treated as
        click and ignored. The rubber band item is removed; the tab will create
        a proper detection via the ValidationModel and a subsequent 
        set_detections() call will add the real item.
        """
        if (
            self._draw_mode
            and self._draw_origin is not None
            and self._draw_rubber_band is not None
        ):
            r = self._draw_rubber_band.rect()

            # Remove the temporary rubber band
            self.removeItem(self._draw_rubber_band)
            self._draw_rubber_band = None
            self._draw_origin = None

            # Ignore very small draws (below minimum size defined in
            #  detection_rect_item.py)
            if r.width() >= MIN_SIZE and r.height() >= MIN_SIZE:
                # Convert to centre format for the signal
                xc = r.x() + r.width() / 2
                yc = r.y() + r.height() / 2
                self.detection_draw_complete.emit(
                    xc, yc, r.width(), r.height()
                )

            # Exit draw mode after one draw
            self._draw_mode = False
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _setup_selection_handling(self) -> None:
        """Connect the scene's selection change to our handler."""
        self.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self) -> None:
        """Emit detection_rect_selected when a detection item is selected."""
        selected = self.selectedItems()
        if len(selected) == 1 and isinstance(selected[0], DetectionRectItem):
            self.detection_rect_selected.emit(selected[0].detection_id)
