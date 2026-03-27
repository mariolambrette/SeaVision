"""YOLO detector implementation using Ultralytics for SeaVision.

This module wraps Ultralytics YOLO to implement the DetectorBase interface, so
it can be used in the SeaVision detection pipeline as a pure, stateless
detector (no built-in tracking or persistence filtering).

Example:
    from seavision.engine.detectors.yolo import YOLODetector, YOLODetectorConfig

    config = YOLODetectorConfig(
        model_path="./models/yolo11n.pt",
        conf_threshold=0.4,
        iou_threshold=0.5,
    )

    with YOLODetector(config) as detector:
        for frame, context in source.iter_frames():
            for det in detector.process_frame(frame, context):
                conf = det.confidence if det.confidence is not None else float("nan")
                print(
                    f"{det.source_file} "
                    f"frame={det.frame_number} "
                    f"label={det.label} "
                    f"conf={conf:.2f}"
                )
"""

import logging
import os
from typing import Iterator, Optional

import numpy as np
import ultralytics

from ...source import FrameContext
from ..base import Detection, DetectorBase
from .config import YOLODetectorConfig

logger = logging.getLogger(__name__)


class YOLODetector(DetectorBase):
    """Object detector based on Ultralytics YOLO.

    This detector implements the DetectorBase interface and produces
    :class:`Detection` objects directly from YOLO predictions. It does **not**
    perform any temporal tracking or persistence filtering; those can be
    composed separately if needed.
    """

    def __init__(self, config: Optional[YOLODetectorConfig] = None):
        """Initialise the YOLO detector.

        Args:
            config: Optional :class:`YOLODetectorConfig`. If None, defaults are
                used.
        """

        # This import will already have been attempted at module import time,
        # but we keep the reference here for clarity and to make the
        # dependency explicit.
        if not hasattr(ultralytics, "YOLO"):
            raise ImportError(
                "Ultralytics YOLO is required for YOLODetector. "
                "Install with: pip install ultralytics>=8.3.237"
            )

        self.config = config or YOLODetectorConfig()

        # Ultralytics model instance (lazy-loaded)
        self._model: Optional[ultralytics.YOLO] = None

        logger.info(
            "YOLODetector initialised (model=%s, device=%s)",
            self.config.model_path,
            self.config.device,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Lazily load the YOLO model from a local path.

        This method is idempotent. It also enforces that the model path exists
        locally to avoid implicit downloads or side-effectful behaviour.
        """

        if self._model is not None:
            return

        if not os.path.exists(self.config.model_path):
            raise FileNotFoundError(
                "YOLO weights not found at: "
                f"{self.config.model_path}. "
                "Download the weights separately and set model_path to the "
                "local file."
            )

        logger.info("Loading YOLO model from %s", self.config.model_path)
        self._model = ultralytics.YOLO(self.config.model_path)

        # Move to device if specified
        if self.config.device:
            try:
                self._model.to(self.config.device)
            except Exception as exc:
                logger.warning(
                    "Failed to move YOLO model to device '%s': %s. "
                    "Using default device instead.",
                    self.config.device,
                    exc,
                )

        logger.info("YOLO model loaded successfully")

    def _class_name_from_id(self, cls_id: int) -> str:
        """Map a YOLO class index to a human-readable name, if available."""

        if self._model is None:
            return str(cls_id)

        names = getattr(self._model, "names", None)

        if isinstance(names, dict):
            return str(names.get(cls_id, cls_id))
        if isinstance(names, (list, tuple)):
            if 0 <= cls_id < len(names):
                return str(names[cls_id])

        return str(cls_id)

    # ------------------------------------------------------------------
    # DetectorBase interface
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame: np.ndarray,
        context: FrameContext,
    ) -> Iterator[Detection]:
        """Process a single video frame and yield YOLO detections.

        Args:
            frame: BGR image as a numpy array with shape (H, W, 3).
            context: FrameContext containing metadata for this frame.

        Yields:
            Detection objects corresponding to YOLO predictions that pass the
            configured confidence and class filters.
        """

        self._ensure_model_loaded()

        # Run YOLO inference on the in-memory frame. All saving-related
        # options are explicitly disabled to avoid side effects.
        results_list = self._model.predict(
            frame,
            imgsz=self.config.imgsz,
            conf=self.config.conf_threshold,
            iou=self.config.iou_threshold,
            max_det=self.config.max_detections,
            classes=self.config.classes,
            device=self.config.device,
            half=self.config.half,
            verbose=self.config.verbose,
            save=False,
            save_frames=False,
            save_txt=False,
            save_conf=False,
            save_crop=False,
            project=None,
            name=None,
        )

        if not results_list:
            return

        results = results_list[0]
        boxes = results.boxes

        if boxes is None or len(boxes) == 0:
            return

        for i in range(len(boxes)):
            box = boxes[i]

            # xyxy format as numpy array
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = xyxy

            width = float(x2 - x1)
            height = float(y2 - y1)
            xc = float(x1 + width / 2.0)
            yc = float(y1 + height / 2.0)

            # Confidence (YOLO already applies conf threshold, but we keep
            # this for completeness and potential future overrides).
            confidence: Optional[float] = None
            if box.conf is not None and len(box.conf) > 0:
                confidence = float(box.conf[0])
                if confidence < self.config.conf_threshold:
                    continue

            # Class index
            cls_id: Optional[int] = None
            if box.cls is not None and len(box.cls) > 0:
                cls_id = int(box.cls[0])

            label: Optional[str] = None
            if self.config.output_labels and cls_id is not None:
                label = self._class_name_from_id(cls_id)

            yield Detection(
                source_file=context.source_file,
                timestamp=context.timestamp,
                frame_number=context.frame_number,
                xc=xc,
                yc=yc,
                width=width,
                height=height,
                confidence=confidence,
                label=label,
                track_id=None,
                mask=None,
            )

    def reset(self) -> None:
        """Reset detector state between videos.

        The YOLO model itself remains loaded; this method exists to satisfy
        the DetectorBase contract and for future extension if needed.
        """

        logger.debug("YOLODetector reset called (no persistent state to clear)")
