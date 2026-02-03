"""
SAM3 detector implementation using Ultralytics integration.

This module wraps SAM3's Ultralytics integration to fit the SeaVision
DetectorBase interface, enabling use in the standard detection pipeline via
the usual configuration process.
"""

import logging
from typing import Dict, Iterator, List, Optional, Tuple
import numpy as np

from engine.source.base import FrameContext
from engine.detectors.base import Detection, DetectorBase
from .config import (
    SAM3DetectorConfig,
    PromptConfig,
    PromptType,
    PrompterConfig,
    HybridStrategy,
)

logger = logging.getLogger(__name__)

# Check for Ultralytics availability
try:
    from ultralytics import SAM
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    SAM = None
    

class SAM3Detector(DetectorBase):
    """
    Promptable concept segmentation detector using metas's SAM3.

    Implements DetectorBase interface for seamless pipeline integration.

    Supports multiple prompting modes:
        - TEXT: Natural language concepts ("fish", "coral reef")
        - BOX: Bounding box exemplars (find similar objects)
        - POINT: Point prompts (SAM 2 style)
        - DETECTOR: Hybrid mode using another detector for prompts

    Video mode enables tracking with memory, maintaining consistent IDs
    across frames and using temporal context for better segmentation.

    Example (text prompts):
        config = SAM3DetectorConfig(prompts=["fish", "coral"])
        
        with SAM3Detector(config) as detector:
            for frame, context in source.iter_frames():
                for detection in detector.process_frame(frame, context):
                    print(f"Found {detection.label} at ({detection.xc}, {detection.yc})")
    
    Example (hybrid with motion detector):
        config = SAM3DetectorConfig(
            prompt_config=PromptConfig(
                prompt_type=PromptType.DETECTOR,
                prompter=PrompterConfig(
                    detector_type="motion",
                    detector_config={"min_area": 200},
                    strategy=HybridStrategy.CLASSIFY_REGIONS,
                    text_prompts=["fish", "marine animal"],
                ),
            ),
        )
        
        with SAM3Detector(config) as detector:
            for frame, context in source.iter_frames():
                for detection in detector.process_frame(frame, context):
                    # Detections are motion candidates classified by SAM 3
                    pass
    
    Note:
        Requires ultralytics>=8.3.237 and the sam3.pt checkpoint.
        GPU (CUDA) strongly recommended for reasonable performance.
    """

    def __init__(self, config: Optional[SAM3DetectorConfig] = None):
        """
        Initialise the SAM3 detector.

        Args:
            config: Configuration, if Nonem defaults are used but text prompts
                are required.

        Raises:
            ImportError: If dependencies are missing.
            ValueError: If configuration is invalid.
            FileNotFoundError: If checkpoint is missing.
        """
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "ultralytics>=8.3.237 is required for SAM 3 support. "
                "Install with: pip install ultralytics>=8.3.237"
            )
        
        self.config = config or SAM3DetectorConfig()

        # Lazily initialised predictors
        self._model: Optional[SAM] = None # type: ignore
        self._video_predictor = None
        self._image_predictor = None
        
        # Prompter detector for hybrid mode
        self._prompter_detector: Optional[DetectorBase] = None

        # State
        self._frame_count: int = 0
        self._video_initialised: bool = False
        self._current_track_ids: Dict[int, int] = {}
        self._next_track_id: int = 0

        # Interactive exemplars (accumulated during session)
        self._positive_boxes: List[List[float]] = []
        self._negative_boxes: List[List[float]] = []

        logger.info(f"SAM3Detector initialised with checkpoint: {self.config.checkpoint}")
        logger.debug(f"Prompt type: {self.config.prompt_config.prompt_type}")
    
    
    def _ensure_model_loaded(self) -> None:
        """Lazily load the SAM3 model."""
        if self._model is not None:
            return
        
        logger.info(f"Loading SAM3 model from checkpoint: {self.config.checkpoint}")

        try:
            self._model = SAM(self.config.checkpoint)

            # Move to device
            if self.config.device != "cpu":
                self._model.to(self.config.device)

            logger.info(f"SAM3 model loaded on {self.config.device}")
        except Exception as e:
            raise RuntimeError (f"Failed to load SAM3 model: {e}")
    
    
    def _ensure_prompter_detector(self) -> None:
        """Lazily initialise the prompt-generating detector for hybrid mode."""
        if self._prompter_detector is not None:
            return
        
        if self.config.prompt_config.prompt_type != PromptType.DETECTOR:
            return
        
        prompter_cfg = self.config.prompt_config.prompter
        if prompter_cfg is None:
            raise ValueError("Prompter configuration is required for DETECTOR prompt type.")
        
        detector_type = prompter_cfg.detector_type
        logger.info(f"Initialising prompter detector: {detector_type}")

        # Built in detector types
        if detector_type == "motion":
            from engine.detectors.motion import MotionDetector, MotionDetectorConfig
            
            # Parse config
            motion_cfg = MotionDetectorConfig(
                stabilisation_enabled=prompter_cfg.detector_config.get(
                    "stabilisation_enabled", True
                ),
                min_area=prompter_cfg.detector_config.get("min_area", 500),
                max_area=prompter_cfg.detector_config.get("max_area", 50000),
                morph_kernel_size=prompter_cfg.detector_config.get(
                    "morph_kernel_size", 5
                ),
                morph_iterations=prompter_cfg.detector_config.get(
                    "morph_iterations", 2
                ),
                persistence_enabled=prompter_cfg.detector_config.get(
                    "persistence_enabled", True
                ),
                min_persistence=prompter_cfg.detector_config.get(
                    "min_persistence", 3
                ),
                max_frames_missing=prompter_cfg.detector_config.get(
                    "max_frames_missing", 5
                ),
                iou_threshold=prompter_cfg.detector_config.get(
                    "iou_threshold", 0.3
                ),
            )
            self._prompter_detector = MotionDetector(motion_cfg)
        
        # TODO: YOLO detector
        # elif detector_type == "yolo":
        #     from engine.detectors.yolo import YOLODetector, YOLODetectorConfig
        #     ...  

        # Try to get from pipeline registry
        else:
            try:
                from pipeline import DETECTOR_REGISTRY
                if detector_type in DETECTOR_REGISTRY:
                    det_class, config_parser = DETECTOR_REGISTRY[detector_type]
                    det_config = config_parser(prompter_cfg.detector_config)
                    self._prompter_detector = det_class(det_config)
                else:
                    raise ValueError(
                        f"Unknown prompter detector type: {detector_type}. "
                        f"Available: motion, or register custom detector."
                    )
            except ImportError:
                raise ValueError(
                    f"Unknown prompter detector type: {detector_type}. "
                    f"Built-in types: motion"
                )
            
        logger.debug(f"Prompter detector initialised: {type(self._prompter_detector)}")

    
    def process_frame(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process frame and yield detections.

        Args:
            frame: BGR image as a numpy arra (H x W x 3).
            context: FrameContext with metadata.

        Yields:
            Detection (or SAM3Detection) for each detected object.
        """

        self._ensure_model_loaded()

        prompt_config = self.config.prompt_config

        # Route to appropiate processing method
        if prompt_config.prompt_type == PromptType.DETECTOR:
            yield from self._process_detector_mode(frame, context)
        elif self.config.video_mode:
            yield from self._process_video_mode(frame, context)
        else:
            yield from self._process_image_mode(frame, context)

        self._frame_count += 1

    
    def _process_image_mode(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process a single image frame in image mode (no tracking).

        Args:
            frame: BGR image as a numpy array (H x W x 3).
            context: FrameContext with metadata.
        """

        prompt_config = self.config.prompt_config

        # Build prompts based on type
        if prompt_config.prompt_type == PromptType.TEXT:
            results = self._model(
                frame,
                texts=prompt_config.text_prompts,
                device=self.config.device,
                verbose=False,
                **self._get_inference_args()
            )

        elif prompt_config.prompt_type == PromptType.BOX:
            # Combined configured bixed with interactive exemplars
            all_boxes = prompt_config.box_prompts + self._positive_boxes
            all_labels = prompt_config.box_labels + [1] * len(self._positive_boxes)

            # Add negative boxes
            all_boxes.extend(self._negative_boxes)
            all_labels.extend([0] * len(self._negative_boxes))

            if not all_boxes:
                logger.warning("No box prompts provided, skipping frame.")
                return

            results = self._model(
                frame,
                bboxes=all_boxes,
                labels=all_labels,
                device=self.config.device,
                verbose=False,
                **self._get_inference_args()
            )

        elif prompt_config.prompt_type == PromptType.POINT:
            if not prompt_config.point_prompts:
                logger.warning("No point prompts provided, skipping frame")
                return
            
            results = self._model(
                frame,
                points=prompt_config.point_prompts,
                labels=prompt_config.point_labels,
                device=self.config.device,
                verbose=False,
                **self._get_inference_args(),
            )
        
        else:
            raise ValueError(f"Unsupported prompt type: {prompt_config.prompt_type}")
        
        # Parse results
        yield from self._parse_results(results, context)

    
    def _process_video_mode(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """Process frame in video mode with tracking and memory."""
        prompt_config = self.config.prompt_config

        # Determine if we should prompt this frame
        should_prompt = self._should_prompt_frame()

        if should_prompt:
            # Full prompting - find all objects
            logger.debug(f"Frame {context.frame_number}: PROMPT mode")
            
            if prompt_config.prompt_type == PromptType.TEXT:
                results = self._model.track(
                    frame,
                    texts=prompt_config.text_prompts,
                    persist=True,
                    device=self.config.device,
                    verbose=False,
                    **self._get_inference_args(),
                )
            elif prompt_config.prompt_type == PromptType.BOX:
                all_boxes = prompt_config.box_prompts + self._positive_boxes
                results = self._model.track(
                    frame,
                    bboxes=all_boxes,
                    persist=True,
                    device=self.config.device,
                    verbose=False,
                    **self._get_inference_args(),
                )
            else:
                # Fall back to text if available
                if prompt_config.text_prompts:
                    results = self._model.track(
                        frame,
                        texts=prompt_config.text_prompts,
                        persist=True,
                        device=self.config.device,
                        verbose=False,
                        **self._get_inference_args(),
                    )
                else:
                    logger.warning(
                        f"Video mode requires TEXT or BOX prompts, "
                        f"got {prompt_config.prompt_type}"
                    )
                    return
            
            self._video_initialised = True

        else:
            # Propagate mode - just track existing objects
            logger.debug(f"Frame {context.frame_number}: PROPAGATE mode")
            
            if not self._video_initialised:
                # First frame must always prompt
                yield from self._process_video_mode(frame, context)
                return
            
            results = self._model.track(
                frame,
                persist=True,
                device=self.config.device,
                verbose=False,
                **self._get_inference_args(),
            )
        
        # Parse results with tracking IDs
        yield from self._parse_results(results, context, with_tracking=True)

    
    def _process_detector_mode(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process frames usning another detector to generate prompts for SAM3.
        """

        self._ensure_prompter_detector()

        prompter_cfg = self.config.prompt_config.prompter

        # Get candidate dections from prompter
        candidates = list(
            self._prompter_detector.process_frame(frame, context)
        )

        if not candidates:
            logger.debug(f"Frame {context.frame_number}: No prompter detections.")
            return

        logger.debug(
            f"Frame {context.frame_number}: {len(candidates)} prompter detections."
        )

        # Convet candidates to boxes
        candidate_boxes = []
        for det in candidates:
            x1, y1, x2, y2 = det.bbox
            candidate_boxes.append([x1, y1, x2, y2])

        # Apply SAM3 based on strategy
        if prompter_cfg.strategy == HybridStrategy.BOX_REFINEMENT:
            # Use boxes directly as SAM 3 prompts
            yield from self._refine_boxes(
                frame, context, candidate_boxes, candidates
            )
        
        elif prompter_cfg.strategy == HybridStrategy.CLASSIFY_REGIONS:
            # Use boxes + text prompts to classify
            yield from self._classify_regions(
                frame, context, candidate_boxes, candidates, prompter_cfg.text_prompts
            )


    def _refine_boxes(
        self,
        frame: np.ndarray,
        context: FrameContext,
        boxes: List[List[float]],
        original_detections: List[Detection]
    ) -> Iterator[Detection]:
        """
        Refine bounding boxes using SAM3 segmentation.
        Takes boxes from prompter detector and produces highquality masks.
        """

        if not boxes:
            return
        
        # Use SAM3 to segment the boxes
        results = self._model(
            frame,
            bboxes=boxes,
            device=self.config.device,
            verbose=False,
            **self._get_inference_args(),
        )

        # Parse results, preserving any labels from original detections
        for i, detection in enumerate(self._parse_results(results, context)):
            # Inherit label from original if SAM 3 didn't provide one
            if detection.label is None and i < len(original_detections):
                original = original_detections[i]
                detection.label = original.label
            
            yield detection


    def _classify_regions(
        self,
        frame: np.ndarray,
        context: FrameContext,
        boxes: List[List[float]],
        original_detections: List[Detection],
        text_prompts: List[str]
    ) -> Iterator[Detection]:
        """
        Classify candidate regions using SAM3 text prompts.

        Asks SAM3 to identify which candidates match the text prompts.
        """

        if not boxes or not text_prompts:
            return
        
        # For each candidate box, ask SAM 3 what's there
        # This is done by running text prompts on the full image and matching
        # results back to the candidate boxes with iou

        # Generate SAM3 detections with text prompts
        results = self._model(
            frame,
            texts=text_prompts,
            device=self.config.device,
            verbose=False,
            **self._get_inference_args(),
        )
        
        # Get SAM 3 detections
        sam3_detections = list(self._parse_results(results, context))
        
        if not sam3_detections:
            logger.debug("SAM 3 found no objects matching text prompts")
            return
        
        # Match SAM3 detections back to candidate boxes by IoU
        prompter_cfg = self.config.prompt_config.prompter
        min_iou = prompter_cfg.min_iou_with_prompt if prompter_cfg else 0.0

        matched_candidates = set()

        for sam3_det in sam3_detections:
            best_iou = 0.0
            best_idx = -1
            
            for i, candidate_box in enumerate(boxes):
                if i in matched_candidates:
                    continue
                
                iou = self._compute_iou(sam3_det.bbox, tuple(candidate_box))
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i
            
            # If IoU threshold met, yield the SAM 3 detection
            if best_iou >= min_iou and best_idx >= 0:
                matched_candidates.add(best_idx)
                yield sam3_det

    
    def _should_prompt_frame(self) -> bool:
        """Determine if current frame should use full prompting."""
        prompt_config = self.config.prompt_config
        
        # First frame always prompts
        if self._frame_count == 0:
            return True
        
        # Check reprompt interval
        if prompt_config.reprompt_interval > 0:
            if self._frame_count % prompt_config.reprompt_interval == 0:
                return True
        
        # Check if tracking was lost (would need state from previous frame)
        # This is a simplified check - full implementation would track confidence
        # TODO: How do we implement the full implementation?
        if prompt_config.reprompt_on_lost and not self._video_initialised:
            return True
        
        return False
    

    def _parse_results(
        self,
        results,
        context: FrameContext,
        with_tracking: bool = False
    ) -> Iterator[Detection]:
        """
        Parse Ultralytics results into Detection objects.

        Args:
            results: Results from SAM3 inference with ultralytics.
            context: FrameContext with metadata.
            with_tracking: Whether to extract tracking IDs.

        Yields:
            Detection objects.
        """
        if results is None:
            return
        
        # Handle list of results
        if isinstance(results, list):
            results = results[0] if results else None

        if results is None:
            return
        
        # Get boxes
        boxes = results.boxes
        if boxes is None or len(boxes) == 0:
            return
        
        # Get masks if available
        masks = results.masks

        # Get class name if available
        names = results.names if hasattr(results, "names") else {}

        for i in range(len(boxes)):
            # Get bounding box
            box = boxes[i]
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = xyxy
            
            # Calculate center format
            xc = (x1 + x2) / 2
            yc = (y1 + y2) / 2
            width = x2 - x1
            height = y2 - y1
            
            # Filter by size
            area = width * height
            if area < self.config.min_mask_area:
                continue
            if area > self.config.max_mask_area:
                continue
            
            # Get confidence
            confidence = float(box.conf[0]) if box.conf is not None else None
            
            # Filter by confidence
            if confidence is not None and confidence < self.config.confidence_threshold:
                continue
            
            # Get class/label
            label = None
            if self.config.output_labels:
                if box.cls is not None:
                    cls_id = int(box.cls[0])
                    label = names.get(cls_id, str(cls_id))
                # For text prompts, label might be in different location
                elif hasattr(results, 'texts') and results.texts:
                    # Map detection to text prompt
                    prompt_config = self.config.prompt_config
                    if prompt_config.text_prompts and i < len(prompt_config.text_prompts):
                        label = prompt_config.text_prompts[i]
            
            # Get track ID
            track_id = None
            if with_tracking and box.id is not None:
                sam_track_id = int(box.id[0])
                # Map SAM's track ID to our consistent track ID
                if sam_track_id not in self._current_track_ids:
                    self._current_track_ids[sam_track_id] = self._next_track_id
                    self._next_track_id += 1
                track_id = self._current_track_ids[sam_track_id]
            
            # Get mask
            mask = None
            if self.config.output_masks and masks is not None:
                if i < len(masks):
                    mask = masks[i].data.cpu().numpy().astype(np.uint8) * 255
                    # Ensure mask is 2D
                    if mask.ndim == 3:
                        mask = mask[0]
            
            yield Detection(
                source_file=context.source_file,
                timestamp=context.timestamp,
                frame_number=context.frame_number,
                xc=float(xc),
                yc=float(yc),
                width=float(width),
                height=float(height),
                confidence=confidence,
                label=label,
                track_id=track_id,
                mask=mask,
            )


    def _get_inference_args(self) -> dict:
        """Get common inference arguments."""
        return {
            "imgsz": self.config.imgsz,
            "half": self.config.half,
            "conf": self.config.confidence_threshold,
        }
    

    @staticmethod
    def _compute_iou(
        box1: Tuple[float, float, float, float],
        box2: Tuple[float, float, float, float],
    ) -> float:
        """Compute IoU between two boxes in (x1, y1, x2, y2) format."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    

    def add_exemplar(
        self,
        box: List[float],
        positive: bool = True,
    ) -> None:
        """
        Add an interactive exemplar for refinement.
        
        Args:
            box: Bounding box as [x1, y1, x2, y2].
            positive: If True, find similar objects. If False, exclude similar.
        
        Example:
            # User clicks on a fish they want more of
            detector.add_exemplar([100, 150, 200, 250], positive=True)
            
            # User clicks on debris to exclude
            detector.add_exemplar([300, 200, 350, 280], positive=False)
        """
        if positive:
            self._positive_boxes.append(box)
            logger.info(f"Added positive exemplar: {box}")
        else:
            self._negative_boxes.append(box)
            logger.info(f"Added negative exemplar: {box}")

    
    def clear_exemplars(self) -> None:
        """Clear all interactive exemplars."""
        self._positive_boxes.clear()
        self._negative_boxes.clear()
        logger.info("Cleared all exemplars")


    def reset(self) -> None:
        """Reset detector state for a new video."""
        # Reset video state
        self._frame_count = 0
        self._video_initialised = False
        self._current_track_ids.clear()
        self._next_track_id = 0
        
        # Reset prompter detector if present
        if self._prompter_detector is not None:
            self._prompter_detector.reset()
        
        # Clear exemplars
        self.clear_exemplars()
        
        # Reset model tracking state
        if self._model is not None:
            # Ultralytics models may have a reset or new tracking session method
            try:
                self._model.predictor.reset()
            except (AttributeError, TypeError):
                pass
        
        logger.debug("SAM3Detector state reset")

    
    def __enter__(self):
        """Context manager entry."""
        return self

    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.reset()
        return False



