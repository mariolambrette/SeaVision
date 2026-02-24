"""Native SAM3 detector using the official Transformers API.

This module provides a DetectorBase-compatible wrapper around Meta's
"facebook/sam3" image segmentation model exposed via the Hugging Face
Transformers library. It is intended as an alternative to the
Ultralytics-based SAM3 integration used by :class:`SAM3Detector`.

Key characteristics:

- Uses :class:`transformers.Sam3Model` and :class:`transformers.Sam3Processor`
  directly ("native" API), mirroring the behaviour of the official
  SAM3 demo and documentation.
- Operates on video streams frame-by-frame, but treats each frame as an
  independent image segmentation problem and then assigns simple track IDs
  across frames using IoU-based matching.
- Supports TEXT prompts only ("promptable concept segmentation"), using the
  same :class:`SAM3DetectorConfig` and :class:`PromptConfig` as the existing
  Ultralytics-backed detector.
- Emits :class:`engine.detectors.base.Detection` objects, so it integrates
  seamlessly with the rest of the SeaVision pipeline (writers, visualisers
  and post-processors).

Notes
-----
- This implementation focuses on correctness and API parity rather than
  maximum performance. For each frame, it runs the SAM3 model once per
  text prompt, similar to how the official demo handles single-text queries.
- The tracking implementation is deliberately simple (greedy IoU matching)
  and is intended to provide stable track IDs for downstream consumers
  (e.g. motion-based filters), rather than fully replicating SAM3's
  internal video-tracking behaviour.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterator, List, Optional

import numpy as np
import torch
from PIL import Image

from engine.source import FrameContext
from engine.detectors.base import Detection, DetectorBase
from .config import SAM3DetectorConfig, PromptConfig, PromptType

logger = logging.getLogger(__name__)


try:  # Optional dependency: Transformers with SAM3 support
    from transformers import Sam3Model, Sam3Processor  # type: ignore

    HF_SAM3_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency guard
    Sam3Model = None  # type: ignore[assignment]
    Sam3Processor = None  # type: ignore[assignment]
    HF_SAM3_AVAILABLE = False


class SAM3NativeDetector(DetectorBase):
    """Native SAM3 detector using the Hugging Face Transformers API.

    This detector provides promptable concept segmentation for video frames
    using the official ``facebook/sam3`` checkpoint. It accepts the same
    :class:`SAM3DetectorConfig` as the Ultralytics-based :class:`SAM3Detector`
    and produces :class:`Detection` objects in the same format so it can be
    dropped into existing SeaVision pipelines.

    Differences vs :class:`SAM3Detector` (Ultralytics backend):

    - Uses :class:`Sam3Model` + :class:`Sam3Processor` (image PCS) rather
      than Ultralytics' ``SAM3VideoSemanticPredictor``.
    - Currently supports **TEXT prompts only** (one or more concepts), using
      per-frame image segmentation rather than the SAM3 video model.
    - Implements a simple IoU-based tracker to maintain ``track_id``
      continuity across frames, instead of relying on SAM3's native video
      tracking state.

    Parameters
    ----------
    config:
        :class:`SAM3DetectorConfig` instance. The following fields are used:

        - ``prompts`` / ``prompt_config.text_prompts``: list of text
          concepts, e.g. ``["fish", "seal"]``.
        - ``confidence_threshold``: minimum score for keeping a mask.
        - ``min_mask_area`` / ``max_mask_area``: area filters (in pixels).
        - ``device``: ``"cuda"``, ``"cpu"``, etc.
        - ``output_masks`` / ``output_labels``: control Detection outputs.

    Raises
    ------
    ImportError
        If the ``transformers`` package with SAM3 support is not installed.
    ValueError
        If the prompt configuration is missing or uses a non-TEXT mode.
    """

    # IoU threshold for associating detections with existing tracks
    _TRACK_IOU_THRESHOLD: float = 0.5
    # Maximum age (in frames) for keeping tracks without updates
    _MAX_TRACK_AGE_FRAMES: int = 30

    def __init__(self, config: Optional[SAM3DetectorConfig] = None):
        if not HF_SAM3_AVAILABLE:
            raise ImportError(
                "SAM3NativeDetector requires the 'transformers' package with "
                "SAM3 support. Install with: pip install 'transformers>=4.47' "
                "and ensure the facebook/sam3 checkpoint is available."
            )

        self.config: SAM3DetectorConfig = config or SAM3DetectorConfig()

        # Ensure we have a TEXT prompt configuration
        prompt_cfg: Optional[PromptConfig] = self.config.prompt_config
        if prompt_cfg is None:
            if self.config.prompts:
                prompt_cfg = PromptConfig(
                    prompt_type=PromptType.TEXT,
                    text_prompts=self.config.prompts,
                )
                self.config.prompt_config = prompt_cfg
            else:
                raise ValueError(
                    "SAM3NativeDetector requires text prompts. Provide "
                    "SAM3DetectorConfig(prompts=[...]) or a PromptConfig "
                    "with prompt_type=TEXT."
                )

        if prompt_cfg.prompt_type != PromptType.TEXT:
            raise ValueError(
                "SAM3NativeDetector currently supports only TEXT prompts. "
                f"Got prompt_type={prompt_cfg.prompt_type!r}."
            )

        if not prompt_cfg.text_prompts:
            raise ValueError(
                "No text prompts specified. Provide text_prompts in the "
                "PromptConfig or use the 'prompts' shorthand in "
                "SAM3DetectorConfig."
            )

        self._device = torch.device(self.config.device)

        # Lazily loaded native SAM3 components
        self._model: Optional[Sam3Model] = None  # type: ignore[assignment]
        self._processor: Optional[Sam3Processor] = None  # type: ignore[assignment]

        # Video / tracking state
        self._current_source_file: Optional[str] = None
        self._frame_count: int = 0

        # Simple track state: track_id -> {"bbox": (x1,y1,x2,y2), "label": str, "last_frame": int}
        self._tracks: Dict[int, Dict] = {}
        self._next_track_id: int = 0

        logger.info("SAM3NativeDetector initialised")
        logger.info("  Backend  : Hugging Face Sam3Model (image PCS)")
        logger.info("  Device   : %s", self._device)
        logger.info("  Prompts  : %s", prompt_cfg.text_prompts)

    # ------------------------------------------------------------------
    # Model loading and video state management
    # ------------------------------------------------------------------
    def _ensure_model_loaded(self) -> None:
        """Lazily load the native SAM3 model and processor.

        By default this loads the official ``facebook/sam3`` checkpoint from
        Hugging Face. You can override the model identifier or use a fully
        offline local path by setting ``SAM3DetectorConfig.checkpoint`` to
        either a local directory or a different model ID.

        If the environment variable ``HF_TOKEN`` is set, it will be passed to
        ``from_pretrained`` to authenticate against gated repositories.
        """

        if self._model is not None and self._processor is not None:
            return

        # Allow overriding the model via config.checkpoint. This can be either
        # a local path (for offline use) or a Hugging Face model ID.
        model_name_or_path = getattr(self.config, "checkpoint", None) or "facebook/sam3"

        # Optional token for gated repos
        import os

        hf_token = os.environ.get("HF_TOKEN")

        logger.info(
            "Loading native SAM3 model '%s' on %s (token: %s)",
            model_name_or_path,
            self._device,
            "set" if hf_token else "not set",
        )

        model_kwargs = {"token": hf_token} if hf_token else {}

        # Use default dtype from the checkpoint; mixed precision can be
        # controlled externally if desired.
        self._model = Sam3Model.from_pretrained(  # type: ignore[call-arg]
            model_name_or_path,
            **model_kwargs,
        ).to(self._device)
        self._processor = Sam3Processor.from_pretrained(  # type: ignore[call-arg]
            model_name_or_path,
            **model_kwargs,
        )

        self._model.eval()
        logger.info("Native SAM3 model loaded successfully")

    def _on_video_change(self, context: FrameContext) -> None:
        """Reset tracking state when the video source changes.

        This is called automatically when ``context.source_file`` differs
        from the previously seen source. It clears the internal track
        dictionary and frame counter, ensuring that detections from
        different videos are not linked together.
        """

        if self._current_source_file is not None:
            logger.debug(
                "Video changed from %s to %s",
                self._current_source_file,
                context.source_file,
            )

        self._current_source_file = context.source_file
        self._frame_count = 0
        self._tracks.clear()
        self._next_track_id = 0

    # ------------------------------------------------------------------
    # Core DetectorBase implementation
    # ------------------------------------------------------------------
    def process_frame(
        self,
        frame: np.ndarray,
        context: FrameContext,
    ) -> Iterator[Detection]:
        """Process a single video frame and yield detections.

        For each configured text prompt, this method runs the native SAM3
        image model to obtain segmentation masks for matching concepts.
        Masks are converted into :class:`Detection` objects, filtered by
        area and confidence, and then assigned simple track IDs based on
        IoU with tracks from previous frames.
        """

        self._ensure_model_loaded()

        # Reset state when the video source changes
        if context.source_file != self._current_source_file:
            self._on_video_change(context)

        prompt_cfg = self.config.prompt_config
        assert prompt_cfg is not None  # validated in __init__
        text_prompts = prompt_cfg.text_prompts

        all_detections: List[Detection] = []

        # Run SAM3 once per text concept, similar to the HF demo's usage.
        for text in text_prompts:
            detections_for_prompt = self._run_single_prompt(frame, context, text)
            all_detections.extend(detections_for_prompt)

        # Assign / update track IDs based on IoU with existing tracks
        self._assign_tracks(all_detections, context.frame_number)

        # Yield detections for this frame
        for det in all_detections:
            yield det

        self._frame_count += 1

    # ------------------------------------------------------------------
    # Prompt processing helpers
    # ------------------------------------------------------------------
    def _run_single_prompt(
        self,
        frame: np.ndarray,
        context: FrameContext,
        text_prompt: str,
    ) -> List[Detection]:
        """Run SAM3 for a single text prompt on the given frame.

        Parameters
        ----------
        frame:
            BGR image as a ``numpy.ndarray`` with shape ``(H, W, 3)``.
        context:
            Frame metadata (timestamp, frame_number, source_file, etc.).
        text_prompt:
            Single natural-language concept to segment (e.g. ``"fish"``).

        Returns
        -------
        list of :class:`Detection`
            One Detection per accepted mask instance for this prompt.
        """

        assert self._processor is not None
        assert self._model is not None

        # Convert BGR (OpenCV-style) to RGB for the processor
        rgb = frame[:, :, ::-1]
        pil_image = Image.fromarray(rgb)

        # Build model inputs using the native processor
        model_inputs = self._processor(
            images=pil_image,
            text=text_prompt,
            return_tensors="pt",
        ).to(self._device)

        with torch.no_grad():
            outputs = self._model(**model_inputs)

        # Post-process to obtain per-instance masks and scores
        processed = self._processor.post_process_instance_segmentation(
            outputs,
            threshold=self.config.confidence_threshold,
            mask_threshold=0.5,
            target_sizes=model_inputs.get("original_sizes").tolist(),
        )[0]

        masks = processed.get("masks")
        scores = processed.get("scores")

        if masks is None or scores is None:
            return []

        # Convert to numpy for geometric processing
        masks_np = masks.cpu().numpy()
        scores_np = scores.cpu().numpy()

        detections: List[Detection] = []

        for mask_arr, score in zip(masks_np, scores_np):
            conf = float(score)
            if conf < self.config.confidence_threshold:
                continue

            # Binary mask (True where object present)
            binary_mask = mask_arr > 0.5
            if not binary_mask.any():
                continue

            # Bounding box from mask extents
            rows = np.any(binary_mask, axis=1)
            cols = np.any(binary_mask, axis=0)

            if not rows.any() or not cols.any():
                continue

            y_indices = np.where(rows)[0]
            x_indices = np.where(cols)[0]
            y1, y2 = y_indices[0], y_indices[-1]
            x1, x2 = x_indices[0], x_indices[-1]

            width = x2 - x1
            height = y2 - y1
            area = width * height

            if area < self.config.min_mask_area:
                continue
            if area > self.config.max_mask_area:
                continue

            # Optionally include the raw mask in the Detection
            mask_out = None
            if self.config.output_masks:
                mask_out = (binary_mask.astype(np.uint8) * 255)

            det = Detection.from_bbox(
                source_file=context.source_file,
                timestamp=context.timestamp,
                frame_number=context.frame_number,
                x1=float(x1),
                y1=float(y1),
                x2=float(x2),
                y2=float(y2),
                confidence=conf,
                label=text_prompt if self.config.output_labels else None,
                mask=mask_out,
            )

            detections.append(det)

        return detections

    # ------------------------------------------------------------------
    # Tracking helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _bbox_iou(bbox_a: tuple, bbox_b: tuple) -> float:
        """Compute IoU between two ``(x1, y1, x2, y2)`` boxes."""

        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area_a = max((ax2 - ax1) * (ay2 - ay1), 0.0)
        area_b = max((bx2 - bx1) * (by2 - by1), 0.0)

        union = area_a + area_b - inter_area
        if union <= 0.0:
            return 0.0

        return float(inter_area / union)

    def _assign_tracks(self, detections: List[Detection], frame_number: int) -> None:
        """Assign or update track IDs for the detections in this frame.

        The algorithm is a simple greedy IoU-based tracker:

        - For each detection, find the best matching existing track with the
          same label and IoU above :attr:`_TRACK_IOU_THRESHOLD`.
        - If a match is found, reuse the track ID and update its state.
        - Otherwise, create a new track ID for the detection.
        - Tracks that have not been updated for more than
          :attr:`_MAX_TRACK_AGE_FRAMES` frames are pruned.
        """

        if not detections and not self._tracks:
            return

        # Prune very old tracks
        for track_id in list(self._tracks.keys()):
            last_frame = self._tracks[track_id]["last_frame"]
            if frame_number - last_frame > self._MAX_TRACK_AGE_FRAMES:
                del self._tracks[track_id]

        for det in detections:
            best_track_id: Optional[int] = None
            best_iou = 0.0

            det_bbox = det.bbox
            det_label = det.label

            for track_id, track_state in self._tracks.items():
                if det_label is not None and track_state["label"] != det_label:
                    continue

                iou = self._bbox_iou(det_bbox, track_state["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is not None and best_iou >= self._TRACK_IOU_THRESHOLD:
                # Reuse existing track
                det.track_id = best_track_id
                self._tracks[best_track_id]["bbox"] = det_bbox
                self._tracks[best_track_id]["last_frame"] = frame_number
            else:
                # Start a new track
                new_id = self._next_track_id
                self._next_track_id += 1

                det.track_id = new_id
                self._tracks[new_id] = {
                    "bbox": det_bbox,
                    "label": det_label,
                    "last_frame": frame_number,
                }

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset detector and tracking state.

        This clears the current video context, frame counter and internal
        track dictionary. The underlying SAM3 model and processor remain
        loaded so that subsequent videos do not pay the model load cost
        again.
        """

        self._current_source_file = None
        self._frame_count = 0
        self._tracks.clear()
        self._next_track_id = 0
