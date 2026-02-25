"""
SAM3 detector implementation using Ultralytics integration.

This module wraps SAM3's Ultralytics integration to fit the SeaVision
DetectorBase interface, enabling use in the standard detection pipeline via
the usual configuration process.

SAM3 (Segment Anything Model 3) provides promptable segmentation capabilities
with support for:
- Text prompts: Natural language concepts like "fish", "coral reef"
- Box prompts: Bounding box exemplars to find similar objects
- Point prompts: Click-based prompts (requires base SAM3Predictor)
- Hybrid mode: Using another detector to generate prompts for SAM3

Two inference modes are available:
- Image mode: Frame-by-frame segmentation without tracking
- Video mode: Segmentation with tracking and temporal context
"""

import logging
import os
from typing import Dict, Iterator, List, Optional, Tuple
import numpy as np
import torch

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
    from ultralytics.models.sam import (
        SAM3Predictor, SAM3SemanticPredictor, SAM3VideoSemanticPredictor
    ) 
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    SAM3Predictor = None
    SAM3SemanticPredictor = None
    SAM3VideoSemanticPredictor = None


class SAM3Detector(DetectorBase):
    """
    Promptable concept segmentation detector using Meta's SAM3.

    This detector implements the DetectorBase interface for seamless integration
    with the SeaVision detection pipeline. It leverages SAM3's advanced 
    segmentation capabilities to detect objects based on various prompt types.

    Two inference modes are available:
        - Image mode (video_mode=False): Frame-by-frame segmentation without 
          tracking. Each frame is processed independently.
        - Video mode (video_mode=True): Segmentation with tracking and temporal
          context. Maintains consistent object IDs across frames.

    Supported prompting modes:
        - TEXT: Natural language concepts (e.g., "fish", "coral reef"). Uses
          SAM3's semantic understanding to segment matching objects.
        - BOX: Bounding box exemplars. Finds and segments objects similar to
          the provided box regions.
        - POINT: Point prompts (SAM2 style). Note: Requires base SAM3Predictor,
          not the semantic predictor. Limited support in current implementation.
        - DETECTOR: Hybrid mode using another detector (e.g., motion detector)
          to generate prompts that SAM3 then refines or classifies.

    Attributes:
        config (SAM3DetectorConfig): Configuration for the detector.
        uri (str): Not used, inherited from base class pattern.

    Example (text prompts - image mode):
        >>> config = SAM3DetectorConfig(
        ...     prompt_config=PromptConfig(
        ...         prompt_type=PromptType.TEXT,
        ...         text_prompts=["fish", "coral"]
        ...     )
        ... )
        >>> with SAM3Detector(config) as detector:
        ...     for frame, context in source.iter_frames():
        ...         for detection in detector.process_frame(frame, context):
        ...             print(f"Found {detection.label} at ({detection.xc}, {detection.yc})")

    Example (video mode with tracking):
        >>> config = SAM3DetectorConfig(
        ...     prompt_config=PromptConfig(
        ...         prompt_type=PromptType.TEXT,
        ...         text_prompts=["fish"]
        ...     ),
        ...     video_mode=True,
        ... )
        >>> with SAM3Detector(config) as detector:
        ...     for frame, context in source.iter_frames():
        ...         for detection in detector.process_frame(frame, context):
        ...             print(f"Track {detection.track_id}: {detection.label}")

    Example (hybrid mode - motion detector provides prompts):
        >>> config = SAM3DetectorConfig(
        ...     prompt_config=PromptConfig(
        ...         prompt_type=PromptType.DETECTOR,
        ...         prompter=PrompterConfig(
        ...             detector_type="motion",
        ...             strategy=HybridStrategy.CLASSIFY_REGIONS,
        ...             text_prompts=["fish", "debris"],
        ...         ),
        ...     ),
        ... )

    Example (interactive refinement with exemplars):
        >>> detector = SAM3Detector(config)
        >>> # Add positive exemplar - find similar objects
        >>> detector.add_exemplar(box=[100, 100, 200, 200], positive=True)
        >>> # Add negative exemplar - exclude similar regions
        >>> detector.add_exemplar(box=[300, 300, 350, 350], positive=False)
        >>> for detection in detector.process_frame(frame, context):
        ...     print(detection)

    Note:
        - Requires ultralytics>=8.3.237 and the sam3.pt checkpoint.
        - GPU (CUDA) strongly recommended for reasonable performance.
        - The checkpoint file should be placed at ./models/sam3.pt or the path
          specified via the checkpoint parameter.

    See Also:
        - SAM3DetectorConfig: Configuration options for this detector.
        - PromptConfig: Configuration for different prompt types.
        - Detection: The output detection format.
    """

    def __init__(self, config: Optional[SAM3DetectorConfig] = None):
        """
        Initialise the SAM3 detector.

        Sets up the detector with the provided configuration, validates prompt
        settings, and prepares internal state for processing. The actual model
        loading is deferred until first use (lazy initialisation).

        Args:
            config: Configuration for the detector. If None, defaults are used
                but text prompts will be required before processing can begin.

        Raises:
            ImportError: If ultralytics>=8.3.237 is not installed.
            ValueError: If prompt configuration is invalid (e.g., TEXT mode
                without any text prompts specified).

        Example:
            >>> # Basic initialisation with text prompts
            >>> config = SAM3DetectorConfig(
            ...     prompt_config=PromptConfig(
            ...         prompt_type=PromptType.TEXT,
            ...         text_prompts=["fish", "shark"]
            ...     )
            ... )
            >>> detector = SAM3Detector(config)

            >>> # Initialisation with video mode for tracking
            >>> config = SAM3DetectorConfig(
            ...     prompt_config=PromptConfig(
            ...         prompt_type=PromptType.TEXT,
            ...         text_prompts=["fish"]
            ...     ),
            ...     video_mode=True,
            ...     confidence_threshold=0.5,
            ... )
            >>> detector = SAM3Detector(config)
        """
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "ultralytics>=8.3.237 is required for SAM 3 support. "
                "Install with: pip install ultralytics>=8.3.237"
            )
        
        self.config = config or SAM3DetectorConfig()

        # Validate prompts
        self._validate_prompt_config()

        # Lazily initialised predictors
        self._predictor = None
        self._is_video_mode = self.config.video_mode

        # Prompter detector for hybrid mode
        self._prompter_detector: Optional[DetectorBase] = None

        # Video mode state
        self._video_initialised = False
        self._current_source_file = None

        # Frame counter
        self._frame_count: int = 0

        # Track IDs for consistent mapping
        self._current_track_ids: Dict[int, int] = {}
        self._next_track_id: int = 0    

        # Interactive exemplars (for box/point refinement)
        self._positive_boxes: List[List[float]] = []
        self._negative_boxes: List[List[float]] = []
        self._positive_points: List[List[float]] = []
        self._negative_points: List[List[float]] = []        

        logger.info(f"SAM3Detector initialised")
        logger.info(f"  Mode: {'video (tracking)' if self._is_video_mode else 'image (independent)'}")
        logger.info(f"  Checkpoint: {self.config.checkpoint}")
        if self.config.prompt_config:
            logger.info(f"  Prompt type: {self.config.prompt_config.prompt_type}")
            if self.config.prompt_config.text_prompts:
                logger.info(f"  Text prompts: {self.config.prompt_config.text_prompts}")


    def _validate_prompt_config(self) -> None:
        """
        Validate the prompt configuration.
        
        Raises:
            ValueError: If prompt configuration is missing or invalid.
        """
        prompt_config = self.config.prompt_config
        
        if prompt_config is None:
            raise ValueError(
                "No prompts specified. Provide prompts like: "
                "SAM3DetectorConfig(prompts=['fish', 'coral']) or use "
                "prompt_config for advanced options."
            )
        
        if prompt_config.prompt_type == PromptType.TEXT and not prompt_config.text_prompts:
            raise ValueError(
                "No text prompts specified for TEXT mode. Provide prompts like: "
                "SAM3DetectorConfig(prompts=['fish', 'coral'])"
            )

    
    def _ensure_predictor_loaded(self) -> None:
        """
        Lazily load the appropriate SAM3 predictor.

        This method handles the deferred loading of the SAM3 model, which is
        beneficial for memory management and startup time. The predictor is
        loaded on first use rather than at initialisation.

        The method selects between SAM3VideoSemanticPredictor (for video mode
        with tracking) and SAM3SemanticPredictor (for image mode) based on
        the configuration.

        Raises:
            FileNotFoundError: If the SAM3 checkpoint file is not found at
                the configured path.
            RuntimeError: If the model fails to load for any other reason.

        Note:
            This method is idempotent - calling it multiple times has no
            additional effect after the predictor is loaded.
        """
        if self._predictor is not None:
            return
        
        # Check if checkpoint exists
        if not os.path.exists(self.config.checkpoint):
            raise FileNotFoundError(
                f"SAM 3 checkpoint not found: {self.config.checkpoint}\n"
                f"Expected location: {os.path.abspath(self.config.checkpoint)}\n"
                f"Download from: https://huggingface.co/facebook/sam3\n"
                f"Then place in ./models/sam3.pt or specify path via checkpoint parameter."
            )

        logger.info(f"Loading SAM3 model from checkpoint: {self.config.checkpoint}")

        # Build overrides dict
        overrides = {
            "conf": self.config.confidence_threshold,
            "task": "segment",
            "mode": "predict",
            "model": self.config.checkpoint,
            "half": self.config.half,
            "imgsz": self.config.imgsz,
            "device": self.config.device,
            "verbose": False,
        }

        try:
            if self._is_video_mode:
                self._predictor = SAM3VideoSemanticPredictor(overrides=overrides)
                logger.info("SAM3 Video predictor loaded (tracking enabled)")
            else:
                self._predictor = SAM3SemanticPredictor(overrides=overrides)
                logger.info("SAM3 Image predictor loaded (independent frames)")
            
            logger.info(f"SAM3 {'Video' if self._is_video_mode else 'Image'} predictor loaded")
            
        except Exception as e:
            raise RuntimeError(f"Failed to load SAM 3 model: {e}")
    
    
    def _ensure_prompter_detector(self) -> None:
        """
        Lazily initialise the prompt-generating detector for hybrid mode.

        In hybrid mode (PromptType.DETECTOR), another detector is used to
        generate candidate regions which SAM3 then refines or classifies.
        This method initialises that prompter detector based on the
        configuration.

        Supported prompter detector types:
            - "motion": Uses the built-in MotionDetector
            - Custom types: Looked up in the pipeline's detector registry

        Raises:
            ValueError: If the prompter configuration is missing when required,
                or if the specified detector type is not recognised.

        Note:
            This method is only called when prompt_type is DETECTOR.
            It is idempotent - multiple calls have no additional effect.
        """
        if self._prompter_detector is not None:
            return
        
        if self.config.prompt_config.prompt_type != PromptType.DETECTOR:
            return
        
        prompter_cfg = self.config.prompt_config.prompter
        if prompter_cfg is None:
            raise ValueError(
                "Prompter configuration is required for DETECTOR prompt type."
            )
        
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
        Process a single video frame and yield detections.

        This is the main entry point for detection. It handles:
        1. Lazy loading of the SAM3 model
        2. Detection of video source changes (for state reset)
        3. Routing to the appropriate processing method based on prompt type
        4. Yielding Detection objects for each segmented instance

        Args:
            frame: BGR image as a numpy array with shape (H, W, 3).
                The frame should be in OpenCV's default BGR colour format.
            context: FrameContext containing metadata about the current frame,
                including source file path, frame number, timestamp, and FPS.

        Yields:
            Detection objects for each segmented instance found in the frame.
            Each Detection includes:
            - Bounding box (xc, yc, width, height)
            - Confidence score (if available)
            - Label (if output_labels is enabled and text prompts provided)
            - Track ID (in video mode only)
            - Mask (if output_masks is enabled)

        Raises:
            ValueError: If an unsupported prompt type is configured.

        Example:
            >>> for frame, context in video_source.iter_frames():
            ...     for detection in detector.process_frame(frame, context):
            ...         print(f"Frame {context.frame_number}: "
            ...               f"{detection.label} at ({detection.xc:.0f}, {detection.yc:.0f})")

        Note:
            In video mode, the detector maintains state across frames. When the
            source file changes, internal state is automatically reset.
        """

        self._ensure_predictor_loaded()

        # Check for video change (reset state if source file changes)
        if context.source_file != self._current_source_file:
            self._on_video_change(context)
        
        prompt_config = self.config.prompt_config

        # Route to appropriate processing method based on prompt type
        if prompt_config.prompt_type == PromptType.DETECTOR:
            yield from self._process_hybrid_mode(frame, context)
        elif prompt_config.prompt_type == PromptType.TEXT:
            yield from self._process_text_mode(frame, context)
        elif prompt_config.prompt_type == PromptType.BOX:
            yield from self._process_box_mode(frame, context)
        elif prompt_config.prompt_type == PromptType.POINT:
            yield from self._process_point_mode(frame, context)
        else:
            raise ValueError(f"Unsupported prompt type: {prompt_config.prompt_type}")
        
        self._frame_count += 1


    def _on_video_change(self, context: FrameContext) -> None:
        """
        Handle transition to a new video file.

        Called when the source file in the FrameContext differs from the
        previously processed source. This resets all video-specific state
        to ensure clean processing of the new video.

        Args:
            context: FrameContext for the first frame of the new video.

        Note:
            This method resets:
            - Video initialisation flag
            - Track ID mappings
            - Prompter detector state (if in hybrid mode)
        """
        if self._current_source_file is not None:
            logger.debug(
                f"Video changed from {self._current_source_file} "
                f"to {context.source_file}"
            )

        self._current_source_file = context.source_file
        self._video_initialised = False

        # Reset track ID mapping for new video
        self._current_track_ids.clear()
        self._next_track_id = 0

        # Reset prompter detector if in hybrid mode
        if self._prompter_detector is not None:
            self._prompter_detector.reset()

    
    def _process_text_mode(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process a single frame using text prompts.

        Uses SAM3's semantic understanding to segment objects matching the
        configured text prompts (e.g., "fish", "coral reef").

        Args:
            frame: BGR image as a numpy array (H, W, 3).
            context: FrameContext with frame metadata.

        Yields:
            Detection objects for each instance matching the text prompts.

        Note:
            The text prompts are configured via prompt_config.text_prompts.
            Each detected instance will have a label corresponding to the
            matched text prompt (if output_labels is enabled).
        """

        prompt_config = self.config.prompt_config
        text_prompts = prompt_config.text_prompts
        
        if not text_prompts:
            logger.warning("No text prompts provided, skipping frame")
            return

        # Optional: combine text prompts with any interactive box exemplars.
        # This mirrors the Hugging Face API where text prompts can be
        # accompanied by positive (label=1) and negative (label=0) boxes.
        bboxes = None
        labels = None

        if self._positive_boxes or self._negative_boxes:
            all_boxes = list(self._positive_boxes) + list(self._negative_boxes)
            labels_list = [1] * len(self._positive_boxes) + [0] * len(self._negative_boxes)

            bboxes = np.array(all_boxes, dtype=np.float32)
            labels = np.array(labels_list, dtype=np.int32)

        if self._is_video_mode:
            yield from self._process_video_frame(
                frame,
                context,
                text=text_prompts,
                bboxes=bboxes,
                labels=labels,
            )
        else:
            yield from self._process_image_frame(
                frame,
                context,
                text=text_prompts,
                bboxes=bboxes,
                labels=labels,
            )


    def _process_box_mode(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process a single frame using box prompts.

        Uses bounding box exemplars to find and segment similar objects.
        Both configured box prompts and interactive exemplars (added via
        add_exemplar) are used.

        Positive boxes indicate "find objects like this region".
        Negative boxes indicate "exclude regions like this".

        Args:
            frame: BGR image as a numpy array (H, W, 3).
            context: FrameContext with frame metadata.

        Yields:
            Detection objects for each segmented instance.

        Note:
            Box prompts should be in [x1, y1, x2, y2] format (xyxy).
            Interactive exemplars can be added at runtime using add_exemplar().
        """
        prompt_config = self.config.prompt_config

        # Combine configured boxes with interactive exemplars
        positive_boxes = list(prompt_config.box_prompts) + self._positive_boxes
        negative_boxes = list(self._negative_boxes)

        if not positive_boxes and not negative_boxes:
            logger.warning("No box prompts provided, skipping frame")
            return

        # Build combined boxes and labels arrays
        # Label 1 = positive (foreground), Label 0 = negative (background)
        all_boxes = positive_boxes + negative_boxes
        labels = [1] * len(positive_boxes) + [0] * len(negative_boxes)

        # Convert to numpy arrays for predictor
        bboxes = np.array(all_boxes, dtype=np.float32)
        labels = np.array(labels, dtype=np.int32)

        if self._is_video_mode:
            yield from self._process_video_frame(
                frame, context, bboxes=bboxes, labels=labels
            )
        else:
            yield from self._process_image_frame(
                frame, context, bboxes=bboxes, labels=labels
            )

    
    def _process_point_mode(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process a single frame using point prompts.

        Point prompts provide click-based interaction similar to SAM2.
        Both configured points and interactive exemplars are used.

        Args:
            frame: BGR image as a numpy array (H, W, 3).
            context: FrameContext with frame metadata.

        Yields:
            Detection objects for each segmented instance.

        Warning:
            Point prompts require SAM3Predictor, not SAM3SemanticPredictor.
            The current implementation uses SAM3SemanticPredictor which has
            limited point support. Consider using BOX mode for similar
            functionality with better support.

        Note:
            Points should be in [x, y] format (pixel coordinates).
            Labels: 1 = positive (foreground), 0 = negative (background).
        """
        prompt_config = self.config.prompt_config

        # Combine configured points with interactive exemplars
        positive_points = list(prompt_config.point_prompts) + self._positive_points
        negative_points = list(self._negative_points)

        # Build labels list
        positive_labels = list(prompt_config.point_labels) if prompt_config.point_labels else []
        # Ensure we have labels for all configured points
        while len(positive_labels) < len(prompt_config.point_prompts):
            positive_labels.append(1)
        # Add labels for interactive positive points
        positive_labels.extend([1] * len(self._positive_points))

        # Combine with negative points
        all_points = positive_points + negative_points
        all_labels = positive_labels + [0] * len(negative_points)

        if not all_points:
            logger.warning("No point prompts provided, skipping frame")
            return

        # Convert to numpy arrays
        points = np.array(all_points, dtype=np.float32)
        labels = np.array(all_labels, dtype=np.int32)

        # Point prompts have limited support in SAM3SemanticPredictor
        # Log a warning but attempt to proceed
        logger.warning(
            "Point prompts have limited support in SAM3SemanticPredictor. "
            "Consider using BOX mode or SAM3Predictor for full point support. "
            "Converting points to small boxes as a workaround."
        )

        # Convert points to small boxes (workaround for semantic predictor)
        # Create a small box around each point
        box_size = 10  # pixels
        bboxes = []
        for point in all_points:
            x, y = point
            bboxes.append([
                x - box_size / 2,
                y - box_size / 2,
                x + box_size / 2,
                y + box_size / 2
            ])

        bboxes = np.array(bboxes, dtype=np.float32)

        if self._is_video_mode:
            yield from self._process_video_frame(
                frame, context, bboxes=bboxes, labels=labels
            )
        else:
            yield from self._process_image_frame(
                frame, context, bboxes=bboxes, labels=labels
            )


    def _process_hybrid_mode(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process a single frame using another detector to generate prompts.

        In hybrid mode, a prompter detector (e.g., motion detector) generates
        candidate regions which SAM3 then processes according to the configured
        strategy:

        - BOX_REFINEMENT: Use detected boxes directly as SAM3 prompts to
          generate refined segmentation masks.
        - CLASSIFY_REGIONS: Use text prompts to classify/label the detected
          regions (requires text_prompts in prompter config).

        Args:
            frame: BGR image as a numpy array (H, W, 3).
            context: FrameContext with frame metadata.

        Yields:
            Detection objects for each processed region.

        Note:
            The prompter detector is configured via prompt_config.prompter.
            Its reset() method is called automatically when the video changes.
        """
        self._ensure_prompter_detector()
        
        prompter_cfg = self.config.prompt_config.prompter
        
        # Get candidate detections from prompter
        candidates = list(self._prompter_detector.process_frame(frame, context))
        
        if not candidates:
            logger.debug(f"Frame {context.frame_number}: No candidates from prompter")
            return
        
        logger.debug(
            f"Frame {context.frame_number}: {len(candidates)} candidates from prompter"
        )
        
        # Convert candidates to boxes (xyxy format)
        candidate_boxes = []
        for det in candidates:
            x1 = det.xc - det.width / 2
            y1 = det.yc - det.height / 2
            x2 = det.xc + det.width / 2
            y2 = det.yc + det.height / 2
            candidate_boxes.append([x1, y1, x2, y2])
        
        bboxes = np.array(candidate_boxes, dtype=np.float32)
        labels = np.ones(len(bboxes), dtype=np.int32)
        
        # Apply SAM3 based on strategy
        if prompter_cfg.strategy == HybridStrategy.BOX_REFINEMENT:
            # Use boxes directly as SAM3 prompts (refine into masks)
            if self._is_video_mode:
                yield from self._process_video_frame(
                    frame, context, bboxes=bboxes, labels=labels
                )
            else:
                yield from self._process_image_frame(
                    frame, context, bboxes=bboxes, labels=labels
                )

        elif prompter_cfg.strategy == HybridStrategy.CLASSIFY_REGIONS:
            # Use text prompts to classify the detected regions
            text_prompts = prompter_cfg.text_prompts
            if text_prompts:
                if self._is_video_mode:
                    yield from self._process_video_frame(
                        frame, context, text=text_prompts, bboxes=bboxes, labels=labels
                    )
                else:
                    yield from self._process_image_frame(
                        frame, context, text=text_prompts, bboxes=bboxes, labels=labels
                    )
            else:
                # Fall back to box refinement if no text prompts
                logger.warning(
                    "CLASSIFY_REGIONS strategy requires text_prompts. "
                    "Falling back to BOX_REFINEMENT."
                )
                if self._is_video_mode:
                    yield from self._process_video_frame(
                        frame, context, bboxes=bboxes, labels=labels
                    )
                else:
                    yield from self._process_image_frame(
                        frame, context, bboxes=bboxes, labels=labels
                    )


    def _process_image_frame(
        self,
        frame: np.ndarray,
        context: FrameContext,
        text: Optional[List[str]] = None,
        bboxes: Optional[np.ndarray] = None,
        labels: Optional[np.ndarray] = None,
        points: Optional[np.ndarray] = None,
    ) -> Iterator[Detection]:
        """
        Process a single frame in image mode (no tracking).

        Each frame is processed independently without temporal context or
        object tracking between frames.

        Args:
            frame: BGR image as a numpy array (H, W, 3).
            context: FrameContext with frame metadata.
            text: Optional list of text prompts for semantic segmentation.
            bboxes: Optional array of bounding boxes, shape (N, 4) in xyxy format.
            labels: Optional array of labels for boxes, shape (N,).
                1 = positive/foreground, 0 = negative/background.

        Yields:
            Detection objects for each segmented instance.
        """
        # Set the image
        self._predictor.set_image(frame)
        
        # Run inference with available prompts
        results = self._predictor(text=text, bboxes=bboxes, labels=labels)
        
        # Reset for next frame
        self._predictor.reset_image()
        
        # Parse results
        yield from self._parse_image_results(results, context, text)

    
    def _process_video_frame(
        self,
        frame: np.ndarray,
        context: FrameContext,
        text: Optional[List[str]] = None,
        bboxes: Optional[np.ndarray] = None,
        labels: Optional[np.ndarray] = None,
        points: Optional[np.ndarray] = None,
    ) -> Iterator[Detection]:
        """
        Process a single frame in video mode (with tracking).

        Maintains temporal context and consistent object IDs across frames.
        The first frame initialises prompts; subsequent frames use the
        established memory for tracking.

        Args:
            frame: BGR image as a numpy array (H, W, 3).
            context: FrameContext with frame metadata.
            text: Optional list of text prompts for semantic segmentation.
            bboxes: Optional array of bounding boxes, shape (N, 4) in xyxy format.
            labels: Optional array of labels for boxes, shape (N,).

        Yields:
            Detection objects for each tracked instance, including track_id.
        """
        # First frame: initialize with prompts
        if not self._video_initialised:
            # Set up the image for the predictor
            self._predictor.set_image(frame)

            # Manually initialise the video inference state to mirror
            # Ultralytics' expected structure when using stream_inference.
            preprocessed = self._predictor.preprocess([frame])
            self._predictor.batch = (None, [frame], None)

            # Ensure per-frame buffers are large enough for this frame index.
            num_frames = max(context.frame_number + 1, 1)
            self._predictor.inference_state = {
                "num_frames": num_frames,
                "tracker_inference_states": [],
                "tracker_metadata": {},
                "text_prompt": None,
                "per_frame_geometric_prompt": [None] * num_frames,
                "im": preprocessed,
            }

            # Add initial prompts (sets text_ids and per-frame prompt entries)
            frame_idx, out = self._predictor.add_prompt(
                frame_idx=context.frame_number,
                text=text,
                bboxes=bboxes,
                labels=labels,
            )
            
            self._video_initialised = True
            
            # Parse initial frame output
            yield from self._parse_video_output(out, context, text)
        else:
            # Grow per-frame buffers if the video is longer than initial estimate
            frame_idx = context.frame_number
            prompt_buf = self._predictor.inference_state.get("per_frame_geometric_prompt")
            if prompt_buf is not None and frame_idx >= len(prompt_buf):
                extend_by = frame_idx - len(prompt_buf) + 1
                prompt_buf.extend([None] * extend_by)
                self._predictor.inference_state["per_frame_geometric_prompt"] = prompt_buf
                # Keep num_frames in sync with the extended buffer
                self._predictor.inference_state["num_frames"] = len(prompt_buf)

            # Update predictor with current frame
            self._predictor.inference_state["im"] = self._predictor.preprocess([frame])
            
            # Run inference on subsequent frames
            with torch.inference_mode():
                out = self._predictor._run_single_frame_inference(
                    frame_idx=frame_idx,
                    reverse=False,
                )
            
            yield from self._parse_video_output(out, context, text)


    def _parse_image_results(
        self,
        results,
        context: FrameContext,
        text_prompts: Optional[List[str]] = None,
    ) -> Iterator[Detection]:
        """
        Parse SAM3SemanticPredictor results into Detection objects.

        Converts the Ultralytics Results format into SeaVision Detection objects,
        applying configured filters (confidence, size) and extracting labels
        from text prompts.

        Args:
            results: Results from SAM3SemanticPredictor. This is a List[Results]
                where the list length equals batch size (always 1 for SAM).
                Each Results object contains ALL detections for that image.
            context: Frame context with metadata.
            text_prompts: Optional text prompts for labelling detections.

        Yields:
            Detection objects meeting filter criteria.

        Note:
            The Results object structure:
            - results.boxes: Bounding boxes with xyxy, conf, cls attributes
            - results.masks: Segmentation masks
        """
        if results is None:
            return
        
        # Handle list of Results - SAM uses batch=1, so we get a list with one element
        # The single Results object contains all N detections for the image
        if isinstance(results, list):
            if not results:
                return
            # Get the single Results object (contains all detections)
            results = results[0]
        
        if results is None:
            return
        
        # Get boxes and masks from the Results object
        boxes = results.boxes
        if boxes is None or len(boxes) == 0:
            return
        
        masks = results.masks
        
        # Iterate over all detections in this frame
        for i in range(len(boxes)):
            box = boxes[i]
            
            # Get bounding box coordinates (xyxy format)
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
            confidence = None
            if box.conf is not None and len(box.conf) > 0:
                confidence = float(box.conf[0])
                
                # Filter by confidence
                if confidence < self.config.confidence_threshold:
                    continue
            
            # Get label
            label = None
            if self.config.output_labels:
                if box.cls is not None and len(box.cls) > 0:
                    cls_id = int(box.cls[0])
                    # Map class ID to text prompt if available
                    if text_prompts and cls_id < len(text_prompts):
                        label = text_prompts[cls_id]
                    else:
                        label = str(cls_id)
            
            # Get mask
            mask = None
            if self.config.output_masks and masks is not None:
                if i < len(masks):
                    mask_data = masks[i].data.cpu().numpy()
                    mask = (mask_data[0] * 255).astype(np.uint8)
            
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
                track_id=None,  # No tracking in image mode
                mask=mask,
            )


    def _parse_video_output(
        self,
        out: dict,
        context: FrameContext,
        text_prompts: Optional[List[str]] = None,
    ) -> Iterator[Detection]:
        """
        Parse SAM3VideoSemanticPredictor output into Detection objects.

        Converts the video predictor's output dictionary into SeaVision Detection
        objects with consistent track IDs across frames.

        Args:
            out: Output dict from video predictor containing:
                - obj_id_to_mask: dict mapping object IDs to mask tensors
                - obj_id_to_score: dict mapping object IDs to confidence scores
                - obj_id_to_cls: dict mapping object IDs to class indices
            context: Frame context with metadata.
            text_prompts: Optional text prompts for labelling detections.

        Yields:
            Detection objects with track_id for consistent tracking.

        Note:
            SAM3's internal object IDs are mapped to sequential track IDs
            (0, 1, 2, ...) for cleaner output. The mapping is maintained
            in self._current_track_ids.
        """
        if out is None:
            return
        
        obj_id_to_mask = out.get("obj_id_to_mask", {})
        obj_id_to_score = out.get("obj_id_to_score", {})
        obj_id_to_cls = out.get("obj_id_to_cls", {})
        
        for obj_id, mask_tensor in obj_id_to_mask.items():
            # Convert mask tensor to numpy
            # .cpu() works for both GPU and CPU tensors
            mask_np = mask_tensor.squeeze().cpu().numpy()
            binary_mask = mask_np > 0
            
            # Skip empty masks
            if not binary_mask.any():
                continue
            
            # Calculate bounding box from mask
            rows = np.any(binary_mask, axis=1)
            cols = np.any(binary_mask, axis=0)
            
            if not rows.any() or not cols.any():
                continue
            
            y_indices = np.where(rows)[0]
            x_indices = np.where(cols)[0]
            y1, y2 = y_indices[0], y_indices[-1]
            x1, x2 = x_indices[0], x_indices[-1]
            
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
            confidence = obj_id_to_score.get(obj_id)
            if confidence is not None and confidence < self.config.confidence_threshold:
                continue
            
            # Get label from class ID
            label = None
            if self.config.output_labels:
                cls_id = obj_id_to_cls.get(obj_id)
                if cls_id is not None:
                    cls_id_int = int(cls_id)
                    if text_prompts and cls_id_int < len(text_prompts):
                        label = text_prompts[cls_id_int]
                    else:
                        label = str(cls_id_int)
            
            # Map SAM3's object ID to our consistent track ID
            if obj_id not in self._current_track_ids:
                self._current_track_ids[obj_id] = self._next_track_id
                self._next_track_id += 1
            track_id = self._current_track_ids[obj_id]
            
            # Get mask
            mask = None
            if self.config.output_masks:
                mask = (binary_mask * 255).astype(np.uint8)
            
            yield Detection(
                source_file=context.source_file,
                timestamp=context.timestamp,
                frame_number=context.frame_number,
                xc=float(xc),
                yc=float(yc),
                width=float(width),
                height=float(height),
                confidence=float(confidence) if confidence is not None else None,
                label=label,
                track_id=track_id,
                mask=mask,
            )


    def add_exemplar(
        self,
        box: Optional[List[float]] = None,
        point: Optional[List[float]] = None,
        positive: bool = False
    ) -> None:
        """
        Add an interactive exemplar for refinement.

        Use this to dynamically add positive or negative examples during
        processing. Positive exemplars help find similar objects; negative
        exemplars help exclude similar regions.

        This is useful for interactive workflows where user feedback can
        improve detection quality by providing additional context.

        Args:
            box: Bounding box as [x1, y1, x2, y2] in xyxy format.
                Mutually exclusive with point.
            point: Point as [x, y] in pixel coordinates.
                Mutually exclusive with box.
            positive: If True, find similar objects (foreground).
                If False, exclude similar regions (background).

        Raises:
            ValueError: If neither box nor point is provided, or if both
                are provided simultaneously.

        Example:
            >>> detector = SAM3Detector(config)
            >>>
            >>> # Add positive box exemplar - "find objects like this"
            >>> detector.add_exemplar(box=[100, 100, 200, 200], positive=True)
            >>>
            >>> # Add negative box exemplar - "exclude regions like this"
            >>> detector.add_exemplar(box=[300, 300, 350, 350], positive=False)
            >>>
            >>> # Add positive point exemplar
            >>> detector.add_exemplar(point=[150, 150], positive=True)
            >>>
            >>> # Process frames with these exemplars
            >>> for detection in detector.process_frame(frame, context):
            ...     print(detection)

        Note:
            Exemplars persist until clear_exemplars() is called or the
            detector is reset. They are combined with configured prompts
            during processing.
        """
        if box is None and point is None:
            raise ValueError("Either box or point must be provided")
        if box is not None and point is not None:
            raise ValueError("Cannot provide both box and point")

        if box is not None:
            if positive:
                self._positive_boxes.append(box)
                logger.info(f"Added positive box exemplar: {box}")
            else:
                self._negative_boxes.append(box)
                logger.info(f"Added negative box exemplar: {box}")
        
        if point is not None:
            if positive:
                self._positive_points.append(point)
                logger.info(f"Added positive point exemplar: {point}")
            else:
                self._negative_points.append(point)
                logger.info(f"Added negative point exemplar: {point}")


    def clear_exemplars(self) -> None:
        """
        Clear all interactive exemplars.

        Removes all positive and negative exemplars (both boxes and points)
        that were added via add_exemplar(). Configured prompts from the
        config are not affected.

        Example:
            >>> detector.add_exemplar(box=[100, 100, 200, 200], positive=True)
            >>> detector.add_exemplar(box=[300, 300, 350, 350], positive=False)
            >>> detector.clear_exemplars()  # Removes both exemplars
        """
        self._positive_boxes.clear()
        self._negative_boxes.clear()
        self._positive_points.clear()
        self._negative_points.clear()
        logger.info("Cleared all exemplars")


    def reset(self) -> None:
        """
        Reset detector state for a new video.

        Clears all internal state including:
        - Frame counter
        - Video initialisation flag
        - Current source file tracking
        - Track ID mappings
        - Prompter detector state (if in hybrid mode)
        - Interactive exemplars
        - Predictor internal state

        This is called automatically when processing a new video source,
        but can also be called manually to force a state reset.

        Example:
            >>> detector.reset()  # Force reset before processing new content
        """
        self._frame_count = 0
        self._video_initialised = False
        self._current_source_file = None
        self._current_track_ids.clear()
        self._next_track_id = 0
        
        if self._prompter_detector is not None:
            self._prompter_detector.reset()
        
        # TODO: Add functionality so that when multiple similar videos are
        # processed sequentially, we can choose to keep exemplars from one video
        # to the next. For now, we clear all exemplars on reset.
        self.clear_exemplars()
        
        # Reset predictor state
        if self._predictor is not None:
            if self._is_video_mode:
                self._predictor.inference_state = {}
            else:
                try:
                    self._predictor.reset_image()
                    self._predictor.reset_prompts()
                except (AttributeError, TypeError):
                    pass
        
        logger.debug("SAM3Detector state reset")


    def __enter__(self):
        """
        Context manager entry.

        Allows the detector to be used with Python's 'with' statement for
        automatic resource cleanup.

        Returns:
            Self for use in the with block.

        Example:
            >>> with SAM3Detector(config) as detector:
            ...     for frame, context in source.iter_frames():
            ...         for detection in detector.process_frame(frame, context):
            ...             print(detection)
        """
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit.

        Performs cleanup by resetting the detector state.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.

        Returns:
            False to propagate any exceptions.
        """
        self.reset()
        return False
