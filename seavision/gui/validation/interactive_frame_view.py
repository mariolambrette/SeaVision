"""
QGraphicsView-based frame viewer with interactive detection overlays.

Provides external interface for modifying display (e.g. set_add_mode,
update_frame etc.) and supports interactive bounding box editing.)
"""

import logging

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QImage, QPainter, QWheelEvent, QKeyEvent
from PySide6.QtWidgets import (
    QGraphicsView,
    QSizePolicy,
)

from seavision.gui.validation.interactive_frame_scene import (
    InteractiveFrameScene,
)

logger = logging.getLogger(__name__)

SCROLL_BAR_STYLE = """
    QGraphicsView {
        border: none;
    }
    QScrollBar:horizontal {
        height: 8px;
        background: transparent;
        margin: 0;
    }
    QScrollBar::handle:horizontal {
        background: rgba(128, 128, 128, 120);
        border-radius: 4px;
        min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover {
        background: rgba(128, 128, 128, 180);
    }
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {
        background: transparent;
        width: 0;
        height: 0;
    }
    QScrollBar:vertical {
        width: 8px;
        background: transparent;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(128, 128, 128, 120);
        border-radius: 4px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(128, 128, 128, 180);
    }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {
        background: transparent;
        width: 0;
        height: 0;
    }
"""

class InteractiveFrameView(QGraphicsView):
    """
    Video frame display with iteractive detection editing.
    
    External interface:
        - update_frame(image, frame_number, timestamp)
        - set_add_mode(enabled)
        - frame_clicked signal (emitted for backward compat; draw mode
          now uses detection_draw_complete on the scene)
        - scene: the InteractiveFrameScene (access detection management)
    """

    # Backward compatibility for previous click-to-add mode - the draw-to-create
    # method not uses scene.detection_draw_complete signal instead.
    frame_clicked = Signal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = InteractiveFrameScene(self)
        self.setScene(self._scene)

        # --- Display settings ---
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(320, 240)

        # Enable scroll bars when zoomed in
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        # Smooth rendering
        self.setRenderHints(
            self.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        # Zoom configuration
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self._zoom_factor = 1.0
        self._min_zoom = 1.0
        self._max_zoom = 20.0

        # Dark background
        self.setStyleSheet("background-color: #1e1e1e; border: none;")
        self.setStyleSheet(SCROLL_BAR_STYLE)
        # Anchor zoom/fit transforms on the centre of the view
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )

        self._frame_loaded = False

    @property
    def scene(self) -> InteractiveFrameScene:
        """Access the underlying scene for detection management."""
        return self._scene
    
    def update_frame(
        self,
        image: QImage,
        frame_number: int,
        timestamp: float,
    ) -> None:
        """
        Display a new frame from the video worker.
        """
        self._scene.update_frame(image)
        if self._zoom_factor == 1.0:
            self._fit_frame()
        self._frame_loaded = True

    def _fit_frame(self) -> None:
        """
        Scale the scene to fit the view while maintaining aspect ratio.

        Scales the view's transformation matrix so that the entire scene rect
        fits within the view's viewport. The advantage is that all items 
        (pixmap, detection rects, handles) scale together with no additional
        work.
        """
        scene_rect = self._scene.sceneRect()
        if scene_rect.isEmpty():
            return  # No frame loaded yet
        self.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        """Re-fit the frame when the widget is resized."""
        if self._zoom_factor == 1.0:
            self._fit_frame()
        super().resizeEvent(event)

    def set_add_mode(self, enabled: bool) -> None:
        """
        Toggle draw-to-create mode.

        When enabled, the cursor changes to crosshair and clicking+dragging
        on the frame draws a new bounding box.
        """
        self._scene.set_draw_mode(enabled)
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Zoom in/out with the scroll wheel.

        Zooms towards the cursor position. The zoom factor is clamped to prevent
        excessive zoom in either direction.
        """
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor

        if event.angleDelta().y() > 0:
            factor = zoom_in_factor
        else:
            factor = zoom_out_factor

        new_zoom = self._zoom_factor * factor
        if new_zoom < self._min_zoom or new_zoom > self._max_zoom:
            return

        self._zoom_factor = new_zoom
        self.scale(factor, factor)

    def pan(self, dx: int, dy: int) -> None:
        """
        Pan the viewport by the given pixel amounts.

        Only effective when zoomed in. Does nothing at default zoom since the
        entire frame is already visible.
        """
        if self._zoom_factor <= 1.0:
            return
        h_bar = self.horizontalScrollBar()
        v_bar = self.verticalScrollBar()
        h_bar.setValue(h_bar.value() + dx)
        v_bar.setValue(v_bar.value() + dy)

    def keyPressEvent(self, event) -> None:
        """
        Suppress default arrow key scrolling.

        QGraphicsView scrolls on arrow keys by default. We block this
        because arrow key behaviour is handled entirely by tab-level
        shortcuts (plain arrows for frame stepping, Shift+arrows for
        panning).
        """
        if event.key() in (
            Qt.Key.Key_Left, Qt.Key.Key_Right,
            Qt.Key.Key_Up, Qt.Key.Key_Down,
        ):
            event.ignore()
            return
        super().keyPressEvent(event)

    def reset_zoom(self) -> None:
        """Reset zoom to fit the entire frame in the view."""
        self._zoom_factor = 1.0
        self._fit_frame()

    @property
    def frame_width(self) -> int:
        return self._scene._frame_width

    @property
    def frame_height(self) -> int:
        return self._scene._frame_height