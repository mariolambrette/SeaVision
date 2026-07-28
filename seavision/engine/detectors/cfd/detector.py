"""Community Fish Detector (CFD) detector for SeaVision.

Wraps the CFD RF-DETR checkpoints (via the ``rfdetr`` package) to implement the
SeaVision :class:`DetectorBase` interface, so CFD can be dropped into the
standard pipeline.

Design notes
------------
- **Single class.** CFD detects one class, "fish".
- **Proposal cap.** RF-DETR emits at most ``num_select`` proposals per image
  (300 for these variants). Lowering ``threshold`` cannot exceed that cap, so
  the recall curve is truncated at 300 predictions/frame.
- **Channel order.** SeaVision passes **BGR** frames (OpenCV convention);
  ``rfdetr.predict()`` expects **RGB**. The conversion is handled here, once,
  as a contiguous view flip — passing BGR straight through would silently
  degrade detection. This is the main integration trap and is dealt with in
  ``process_frame``.
- **Resolution.** ``rfdetr.from_checkpoint`` resolves the training resolution
  from checkpoint metadata (1024 for small/medium, 640 for nano), so there is
  no ``imgsz`` to set. An optional override is exposed via the config.
- **Lazy dependency.** ``rfdetr`` (and its heavy torch stack) is imported only
  on first model load, not at module import, mirroring the other optional
  detectors so lightweight consumers can import SeaVision without it.

Example:
    from seavision.engine.detectors.cfd import CFDDetector, CFDDetectorConfig

    config = CFDDetectorConfig(variant="medium", device="cuda:0")
    with CFDDetector(config) as detector:
        for frame, context in source.iter_frames():
            for det in detector.process_frame(frame, context):
                print(det.label, det.confidence, det.bbox)
"""

from __future__ import annotations

import logging
import os
import tempfile
import urllib.request
from typing import Iterator, List, Optional, Tuple

import numpy as np

from ...source import FrameContext
from ..base import Detection, DetectorBase
from .config import CFDDetectorConfig

logger = logging.getLogger(__name__)


class CFDDetector(DetectorBase):
    """RF-DETR-based Community Fish Detector, wrapped for SeaVision.

    Stateless per frame: no temporal tracking or persistence filtering. The
    model is loaded lazily on the first :meth:`process_frame` call and then
    kept resident; inference does not touch disk after load.
    """

    def __init__(self, config: Optional[CFDDetectorConfig] = None):
        self.config = config or CFDDetectorConfig()

        # rfdetr model handle (lazy-loaded on first inference).
        self._model = None
        # Cached class-name lookup, resolved once from the model.
        self._class_names: Optional[List[str]] = None

        logger.info(
            "CFDDetector initialised (variant=%s, device=%s)",
            self.config.variant,
            self.config.device,
        )

    # ------------------------------------------------------------------
    # Weight resolution
    # ------------------------------------------------------------------

    def _resolve_weights(self) -> Tuple[str, bool]:
        """Return ``(local_path, is_temporary)`` for the checkpoint.

        Resolution order:
          1. An existing local ``weights_path`` — used directly, no download.
          2. Otherwise download the pinned release URL, either to the cache
             (``persist_weights=True``) or to a temp file that the caller must
             delete after loading (``persist_weights=False``).
        """
        # 1. Explicit local file.
        if self.config.weights_path:
            if os.path.isfile(self.config.weights_path):
                logger.info("Using local CFD weights: %s", self.config.weights_path)
                return self.config.weights_path, False
            raise FileNotFoundError(
                f"weights_path set but not found: {self.config.weights_path}"
            )

        url = self.config.resolve_weights_url()
        basename = os.path.basename(url)

        # 2a. Persistent cache: download once, reuse thereafter.
        if self.config.persist_weights:
            cache_dir = self.config.cache_dir or os.path.join(
                tempfile.gettempdir(), "community-fish-detector"
            )
            os.makedirs(cache_dir, exist_ok=True)
            dest = os.path.join(cache_dir, basename)
            if os.path.isfile(dest):
                logger.info("Using cached CFD weights: %s", dest)
                return dest, False
            logger.info("Downloading CFD weights\n  from %s\n  to   %s", url, dest)
            self._download(url, dest)
            return dest, False

        # 2b. Ephemeral: download to a temp file, to be deleted after load.
        fd, tmp_path = tempfile.mkstemp(suffix=".pth", prefix="cfd-")
        os.close(fd)
        logger.info(
            "Downloading CFD weights to ephemeral temp file %s (persist_weights=False)",
            tmp_path,
        )
        self._download(url, tmp_path)
        return tmp_path, True

    @staticmethod
    def _download(url: str, dest: str) -> None:
        """Download ``url`` to ``dest``, cleaning up a partial file on failure."""
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception:
            if os.path.isfile(dest):
                try:
                    os.remove(dest)
                except OSError:
                    pass
            raise

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Lazily import rfdetr, resolve weights, and load the model."""
        if self._model is not None:
            return

        # Lazy import: keep the heavy torch/rfdetr stack out of import time.
        try:
            from rfdetr import from_checkpoint #type: ignore #pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise ImportError(
                "The 'rfdetr' package is required for CFDDetector. "
                "Install with: pip install rfdetr>=1.8.3"
            ) from exc

        weights_path, is_temp = self._resolve_weights()
        try:
            logger.info("Loading CFD RF-DETR checkpoint (device=%s)", self.config.device)
            # from_checkpoint resolves the RF-DETR variant, resolution and
            # (single) class count from checkpoint metadata. device is
            # forwarded to the model constructor.
            self._model = from_checkpoint(weights_path, device=self.config.device)
        finally:
            # Ephemeral weights: the checkpoint is now in memory; drop the file.
            if is_temp and os.path.isfile(weights_path):
                try:
                    os.remove(weights_path)
                    logger.info("Removed ephemeral CFD weights file %s", weights_path)
                except OSError as exc:
                    logger.warning("Could not remove temp weights %s: %s", weights_path, exc)

        if self.config.optimize_for_inference:
            logger.info("Optimising CFD model for inference")
            self._model.optimize_for_inference()

        # Resolve and cache class names once (single class for CFD).
        try:
            names = self._model.class_names
            self._class_names = list(names) if names else None
        except Exception:  # pylint: disable=broad-exception-caught
            self._class_names = None

        resolved_res = getattr(self._model, "resolution", None)
        logger.info(
            "CFD model loaded (resolution=%s, classes=%s)",
            resolved_res,
            self._class_names,
        )

    def _label_for(self, class_id: int) -> str:
        """Map a class id to a label, falling back to 'fish' for CFD."""
        if self._class_names and 0 <= class_id < len(self._class_names):
            return str(self._class_names[class_id])
        return "fish"

    # ------------------------------------------------------------------
    # DetectorBase interface
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame: np.ndarray,
        context: FrameContext,
    ) -> Iterator[Detection]:
        """Run CFD on a single frame and yield detections.

        Args:
            frame: BGR image, shape (H, W, 3), uint8 (OpenCV convention).
            context: Frame metadata.

        Yields:
            :class:`Detection` per predicted box, in original-frame pixel
            coordinates. Confidence is the RF-DETR score; label is the model
            class name ("fish") when ``output_labels`` is set.
        """
        self._ensure_model_loaded()

        # BGR -> RGB. predict() requires RGB; ascontiguousarray gives torch a
        # positive-strided buffer (a bare ::-1 view has negative strides and
        # torch.from_numpy would reject it). include_source_image=False avoids
        # an extra full-frame copy we don't need.
        rgb = np.ascontiguousarray(frame[:, :, ::-1])

        predict_kwargs = {
            "threshold": self.config.threshold,
            "include_source_image": False,
        }
        if self.config.resolution is not None:
            predict_kwargs["shape"] = (self.config.resolution, self.config.resolution)

        detections = self._model.predict(rgb, **predict_kwargs) #type: ignore
        # A single-image input returns a single Detections; be defensive.
        if isinstance(detections, list):
            detections = detections[0] if detections else None
        if detections is None or len(detections) == 0:
            return

        xyxy = detections.xyxy #type: ignore
        conf = getattr(detections, "confidence", None)
        class_id = getattr(detections, "class_id", None)

        for i in range(len(detections)):
            x1, y1, x2, y2 = (float(v) for v in xyxy[i])

            confidence: Optional[float] = None
            if conf is not None:
                confidence = float(conf[i])

            label: Optional[str] = None
            if self.config.output_labels:
                cid = int(class_id[i]) if class_id is not None else 0
                label = self._label_for(cid)

            yield Detection.from_bbox(
                source_file=context.source_file,
                timestamp=context.timestamp,
                frame_number=context.frame_number,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                confidence=confidence,
                label=label,
                track_id=None,
                mask=None,
            )

    def reset(self) -> None:
        """No per-video state to clear; the model stays loaded."""
        pass #pylint: disable=unnecessary-pass
