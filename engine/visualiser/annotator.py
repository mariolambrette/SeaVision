"""Frame annotation - drawing detections on video frames."""

from typing import List, Optional, Tuple
import cv2
import numpy as np
import logging

from engine.detectors.base import Detection
from engine.source.base import FrameContext
from engine.visualiser.config import (
    BoundingBoxStyle,
    LabelStyle,
    LabelPosition,
    OverlayStyle,
)

logger = logging.getLogger(__name__)

class FrameAnnotator:
    """
    Draws detection annotations on video frames.

    Stateless - Can be reused across frames and videos. This is the core 
    rendering component used by both live and post-hoc visualisers.

    Example:
        annotator = FrameAnnotator(box_style, label_style)
        annotated = annotator.annotate_frame(frame, detections)
    """

    def __init__(
        self,
        bbox_style: Optional[BoundingBoxStyle] = None,
        label_style: Optional[LabelStyle] = None,
        overlay_style: Optional[OverlayStyle] = None,
    ):
        """
        Initialise the FrameAnnotator with bounding box, label and overlay 
        styles.
        """
        self._bbox_style = bbox_style or BoundingBoxStyle()
        self._label_style = label_style or LabelStyle()
        self._overlay_style = overlay_style or OverlayStyle()

    
    def annotate_frame(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        context: Optional[FrameContext] = None,
        copy: bool = True
    ) -> np.ndarray:
        """
        Draw all detections and overlays on the given frame.

        Args:
            frame: BGR image as a numpy array (H x W x 3).
            detections: List of Detection objects to render.
            context: Optional FrameContext for frame-level overlays.
            copy: If True, a copy of the frame is made before annotation.
                If False, the frame is annotated in-place.
        
        Returns:
            Annotated frame as a numpy array.
        """

        if copy:
            frame = frame.copy()

        for detection in detections:
            self._draw_detection(frame, detection)
        
        # Draw frame-level overlay is enabled and context provided
        if self._overlay_style.enabled:
            if context is not None:
                self._draw_overlay(frame, context, len(detections))
            else:
                logger.warning(
                    "Overlay style enabled but no FrameContext provided. Not" \
                    " drawing overlay."
                )
        
        return frame
    
    def _draw_detection(
        self,
        frame: np.ndarray,
        detection: Detection
    ) -> None:
        """
        Draw a single detection (box and label)

        Args:
            frame: BGR image as a numpy array (H x W x 3).
            detection: Detection object to render.
        
        Returns:
            None - frame is modified in-place.
        """

        # Convert centre format to corner format
        x1 = int(detection.xc - detection.width / 2)
        y1 = int(detection.yc - detection.height / 2)
        x2 = int(detection.xc + detection.width / 2)
        y2 = int(detection.yc + detection.height / 2)
        
        # Choose colour based on optional per-class mapping
        colour = self._bbox_style.colour
        if (
            self._bbox_style.class_colours is not None
            and detection.label is not None
            and detection.label in self._bbox_style.class_colours
        ):
            colour = self._bbox_style.class_colours[detection.label]

        # Draw bounding box if enabled
        if self._bbox_style.draw_box:
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                colour,
                self._bbox_style.thickness
            )

        # Draw centre point if enabled
        if self._bbox_style.draw_centre:
            centre_colour = (
                self._bbox_style.centre_colour
                or colour
            )

            cv2.circle(
                frame,
                (int(detection.xc), int(detection.yc)),
                self._bbox_style.centre_radius,
                centre_colour,
                -1
            )
        
        # Draw label if enabled
        if self._label_style.enabled:
            self._draw_label(frame, detection, (x1, y1, x2, y2))

    
    def _draw_label(
        self,
        frame: np.ndarray,
        detection: Detection,
        bbox: Tuple[int, int, int, int]
    ) -> None:
        """
        Draw label for a detection.

        Args:
            frame: BGR image as a numpy array (H x W x 3).
            detection: Detection object to render.
            bbox: Bounding box as (x1, y1, x2, y2).
        """

        label_text =  self._format_label(detection)

        if not label_text:
            return
        
        x1, y1, x2, y2 = bbox
        frame_h, frame_w = frame.shape[:2]


        # Get text size for positioning
        (text_w, text_h), baseline = cv2.getTextSize(
            label_text,
            cv2.FONT_HERSHEY_SIMPLEX,
            self._label_style.font_scale,
            self._label_style.font_thickness
        )

        # Calculate position based on config
        text_x, text_y = self._calculate_label_position(
            text_w, text_h, baseline, bbox, frame.shape
        )

        # Draw background if configured
        if self._label_style.background_colour is not None:
            padding = self._label_style.padding
            
            # Calculate background rectangle bounds
            bg_x1 = text_x - padding
            bg_y1 = text_y - text_h - padding
            bg_x2 = text_x + text_w + padding
            bg_y2 = text_y + baseline + padding
            
            # Clamp to frame bounds
            bg_x1_clamped = max(0, bg_x1)
            bg_y1_clamped = max(0, bg_y1)
            bg_x2_clamped = min(frame_w, bg_x2)
            bg_y2_clamped = min(frame_h, bg_y2)
            
            # Only draw if rectangle has positive area after clamping
            if bg_x2_clamped > bg_x1_clamped and bg_y2_clamped > bg_y1_clamped:
                cv2.rectangle(
                    frame,
                    (bg_x1_clamped, bg_y1_clamped),
                    (bg_x2_clamped, bg_y2_clamped),
                    self._label_style.background_colour,
                    -1
                )
        
        # Clamp text position to ensure it starts within frame
        # (OpenCV will clip the rendering, but starting position must be valid)
        text_x = max(0, min(text_x, frame_w - 1))
        text_y = max(text_h, min(text_y, frame_h - 1))
            
        # Draw text
        cv2.putText(
            frame,
            label_text,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            self._label_style.font_scale,
            self._label_style.colour,
            self._label_style.font_thickness
        )

    
    def _format_label(self, detection:Detection) -> str:
        """
        Format the label text for a detection based on configuration.

        Args:
            detection: Detection object to format.
        """

        if self._label_style.custom_format:
            return self._label_style.custom_format.format(
                frame_number=detection.frame_number,
                confidence=detection.confidence or 0.0,
                xc=detection.xc,
                yc=detection.yc,
                width=detection.width,
                height=detection.height,
                label=detection.label or "",
            )

        parts = []
        # Class label text
        if self._label_style.show_label and detection.label is not None:
            parts.append(str(detection.label))
        if self._label_style.show_frame_number:
            parts.append(f"Frame: {detection.frame_number}")
        if self._label_style.show_confidence and detection.confidence is not None:
            parts.append(f"Conf: {detection.confidence:.2f}")
        
        return " ".join(parts) if parts else ""


    def _calculate_label_position(
        self,
        text_w: int,
        text_h: int,
        baseline: int,
        bbox: Tuple[int, int, int, int],
        frame_shape: Tuple[int, ...]
    ) -> Tuple[int, int]:
        """
        Calculate Pixel position for label based on config.
        
        Ensures labels remain within frame bounds, adjusting position if the
        preffered location would place text outside the frame.
        """

        x1, y1, x2, y2 = bbox
        padding = self._label_style.padding
        frame_h, frame_w = frame_shape[:2]

        pos = self._label_style.position
        if pos == LabelPosition.TOP_LEFT:
            x = x1 + padding
            y = y1 - padding - baseline
        elif pos == LabelPosition.TOP_RIGHT:
            x = x2 - text_w - padding
            y = y1 - padding - baseline
        elif pos == LabelPosition.BOTTOM_LEFT:
            x = x1 + padding
            y = y2 + text_h + padding
        elif pos == LabelPosition.BOTTOM_RIGHT:
            x = x2 - text_w - padding
            y = y2 + text_h + padding
        elif pos == LabelPosition.ABOVE:
            x = x1
            y = y1 - padding - baseline
        else:  # BELOW
            x = x1
            y = y2 + text_h + padding
        
        # Ensure text doesn't extend beyond right edge
        if x + text_w > frame_w:
            x = frame_w - text_w - padding
        
        # Ensure text doesn't extend beyond left edge
        if x < padding:
            x = padding
        
        # If label would be above the frame, flip to below the box
        if y - text_h < 0:
            y = y2 + text_h + padding
        
        # If label would be below frame, flip to top of the bbox
        if y + baseline > frame_h:
            y = y1 - padding - baseline

            # If still outside (i.e. bounding box fills frame), clamp to bottom
            if y - text_h < 0:
                y = text_h + padding
        
        return (int(x), int(y))

    
    def _draw_overlay(
        self,
        frame:np.ndarray,
        context: FrameContext,
        detection_count: int
    ) -> None:
        """Draw frame-level overlay information."""

        parts = []

        if self._overlay_style.show_frame_number:
            parts.append(f"Frame: {context.frame_number}")
        if self._overlay_style.show_timestamp:
            parts.append(f"Time: {context.timestamp:.2f}s")
        if self._overlay_style.show_detection_count:
            parts.append(f"Detections: {detection_count}")
        
        if not parts:
            return
        
        text = " | ".join(parts)
        position = self._overlay_style.position
        frame_h, frame_w = frame.shape[:2]

        # Get text size for background
        (text_w, text_h), baseline = cv2.getTextSize(
            text,
            cv2.FONT_HERSHEY_SIMPLEX,
            self._overlay_style.font_scale,
            self._overlay_style.font_thickness
        )

        # Clamp position to frame bounds
        text_x = max(0, min(position[0], frame_w - text_w - 1))
        text_y = max(text_h, min(position[1], frame_h - 1))

        # Draw background
        if self._overlay_style.background_colour is not None:
            padding = 5

            bg_x1 = max(0, text_x - padding)
            bg_y1 = max(0, text_y - text_h - padding)
            bg_x2 = min(frame_w, text_x + text_w + padding)
            bg_y2 = min(frame_h, text_y + baseline + padding)
            
            if bg_x2 > bg_x1 and bg_y2 > bg_y1:
                cv2.rectangle(
                    frame,
                    (bg_x1, bg_y1),
                    (bg_x2, bg_y2),
                    self._overlay_style.background_colour,
                    -1
                )

        # Draw text
        cv2.putText(
            frame,
            text,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            self._overlay_style.font_scale,
            self._overlay_style.colour,
            self._overlay_style.font_thickness
        )
