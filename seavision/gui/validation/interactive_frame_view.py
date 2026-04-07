"""
QGraphicsView-based frame viewer with interactive detection overlays.

Provides external interface for modifying display (e.g. set_add_mode,
update_frame etc.) and supports interactive bounding box editing.)
"""

import logging

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (
    QGraphicsView,
    QSizePolicy,
)

from seavision.gui.validation.interactive_frame_scene import (
    InteractiveFrameScene,
)

logger = logging.getLogger(__name__)

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

        # Disable scroll bars — we always fit the frame to the view
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Smooth rendering
        self.setRenderHints(
            self.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        # Dark background
        self.setStyleSheet("background-color: #1e1e1e; border: none;")

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
        """Refit the frame when the widget is resized."""
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

    @property
    def frame_width(self) -> int:
        return self._scene._frame_width

    @property
    def frame_height(self) -> int:
        return self._scene._frame_height