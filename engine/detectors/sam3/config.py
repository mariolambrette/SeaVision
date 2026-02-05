"""
Configuration dataclasses for the SAM3 detector.

This module defines all configuration options for the SAM3 detector, including:
- Prompt configuration (text, box, point, hybrid modes)
- Detector configuration (model settings, thresholds, output options)
- Prompter configuration (for hybrid mode with other detectors)

Example usage:
    >>> from engine.detectors.sam3.config import (
    ...     SAM3DetectorConfig,
    ...     PromptConfig,
    ...     PromptType,
    ... )
    >>> 
    >>> config = SAM3DetectorConfig(
    ...     prompt_config=PromptConfig(
    ...         prompt_type=PromptType.TEXT,
    ...         text_prompts=["fish", "coral"],
    ...     ),
    ...     confidence_threshold=0.5,
    ...     video_mode=True,
    ... )
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PromptType(Enum):
    """
    Type of prompt to use for SAM3 segmentation.

    Attributes:
        TEXT: Natural language text prompts (e.g., "fish", "coral reef").
            Uses SAM3's semantic understanding to find matching objects.
        BOX: Bounding box prompts in xyxy format.
            Finds objects within or similar to the provided boxes.
        POINT: Point prompts with x, y coordinates.
            Click-based prompts similar to SAM2. Note: Limited support
            in SAM3SemanticPredictor.
        DETECTOR: Hybrid mode using another detector to generate prompts.
            The secondary detector provides candidate regions for SAM3
            to refine or classify.
    """

    TEXT = auto()      # Text concepts
    BOX = auto()       # Bounding box exemplars
    POINT = auto()     # Point prompts (SAM2 style)
    DETECTOR = auto()  # Use another detector to generate prompts


class HybridStrategy(Enum):
    """
    Strategy for hybrid mode (PromptType.DETECTOR).

    Defines how SAM3 uses the detections from the prompter detector.

    Attributes:
        BOX_REFINEMENT: Use detected boxes directly as SAM3 box prompts.
            SAM3 generates refined segmentation masks for each box.
            Good for improving mask quality from coarse detections.
        CLASSIFY_REGIONS: Use text prompts to classify detected regions.
            SAM3 applies semantic labels to the detected regions.
            Requires text_prompts to be set in PrompterConfig.
    """

    BOX_REFINEMENT = auto()
    CLASSIFY_REGIONS = auto()


@dataclass
class PrompterConfig:
    """
    Configuration for the prompt source in hybrid/detector mode.

    In hybrid mode, another detector generates candidate boxes that become
    prompts for SAM3. This allows combining fast detectors (motion/YOLO) with
    SAM3's segmentation and semantic understanding.

    Attributes:
        detector_type: Type of detector to use ("motion", "yolo" or custom).
        detector_config: Configuration dict passed to the detector.
        strategy: How to combine detector output with SAM3.
        text_prompts: Text prompts for CLASSIFY_REGIONS strategy.
        min_iou_with_prompt: Minimum IoU between SAM3 output and original
            detector box to keep the detection (filters false positives).

    Example (motion + SAM3 refinement):
        PrompterConfig(
            detector_type="motion",
            detector_config={"min_area": 200, "persistence_enabled": True},
            strategy=HybridStrategy.BOX_REFINEMENT,
        )
    
    Example (motion finds candidates, SAM3 classifies):
        PrompterConfig(
            detector_type="motion",
            detector_config={"min_area": 100},
            strategy=HybridStrategy.CLASSIFY_REGIONS,
            text_prompts=["fish", "coral", "debris"],  # What to look for
        )
    
    Example (YOLO + SAM3 masks):
        PrompterConfig(
            detector_type="yolo",
            detector_config={"model": "yolov8n.pt", "conf": 0.25},
            strategy=HybridStrategy.BOX_REFINEMENT,
        )
    """

    detector_type: str = "motion"  # "motion", "yolo", or custom
    detector_config: Dict = field(default_factory=dict)
    strategy: HybridStrategy = HybridStrategy.BOX_REFINEMENT
    text_prompts: List[str] = field(default_factory=list)
    min_iou_with_prompt: float = 0.0


@dataclass
class PromptConfig:
    """
    Configuration for SAM3 prompting.

    SAM3 supports multiple prompt types:
    - Text: find all instances of concepts (e.g. "fish", "seal")
    - Box exemplars: Find all similar objects to the boxed example
    - Points: SAM2-style single object segmentation, segments the object at the
        given point(s).
    - Hybrid: Use another detector (e.g. motion, YOLO) to generate prompts

    Attributes:
        prompt_type: The type of prompt to use.

        # For TEXT mode:
        text_prompts: List of text concepts to segment, if using TEXT prompts.
        
        # For BOX mode (manual exemplars):
        box_prompts: List of bounding boxes as [x1, y1, x2, y2], if using BOX 
            prompts.
        box_labels: Labels for box prompts (1=positive, 0=negative).
        
        # For POINT mode:
        point_prompts: List of points as [x, y], if using POINT prompts.
        point_labels: Labels for point prompts (1=positive, 0=negative).

        # For DETECTOR mode (hybrid):
        prompter: Configuration for the prompt-generating detector.

        # Video settings:
        reprompt_interval: Interval (in frames) to re-generate prompts in video.
            For frames between prompts, only existing objects are tracked. This
            is faster than reprompting but means new objects will be missed.
        reprompt_on_lost: Whether to reprompt when tracked objects are lost.
    """

    prompt_type: PromptType = PromptType.TEXT
    
    # TEXT mode:
    text_prompts: List[str] = field(default_factory=list)

    # BOX mode:
    box_prompts: List[List[float]] = field(default_factory=list)
    box_labels: List[int] = field(default_factory=list) 

    # POINT mode:
    point_prompts: List[List[float]] = field(default_factory=list)
    point_labels: List[int] = field(default_factory=list)
    
    # DETECTOR mode (hybrid):
    prompter: Optional[PrompterConfig] = None

    # Video settings:
    reprompt_interval: int = 0
    reprompt_on_lost: bool = False

    def __post_init__(self):
        """Validate configuration."""

        if self.prompt_type == PromptType.TEXT and not self.text_prompts:
            raise ValueError("text_prompts required for TEXT mode.")
        
        if self.prompt_type == PromptType.BOX and not self.box_prompts:
            raise ValueError("box_prompts required for BOX mode.")
        
        if self.prompt_type == PromptType.POINT and not self.point_prompts:
            raise ValueError("point_prompts required for POINT mode.")
        
        if self.prompt_type == PromptType.DETECTOR and self.prompter is None:
            raise ValueError("prompter config required for DETECTOR mode.")
        
        # Default box and point labels to positive:
        if self.box_prompts and not self.box_labels:
            self.box_labels = [1] * len(self.box_prompts)
        if self.point_prompts and not self.point_labels:
            self.point_labels = [1] * len(self.point_prompts)


@dataclass
class SAM3DetectorConfig:
    """
    Configuration for the SAM3 detector with Ultralytics integration.

    Attributes:
        checkpoint: Path to the sam3.pt checkpoint.
        device: Compute device ("cuda", "cpu", "mps", etc.).
        half: Use FP16 for faster inference on supported devices.
        
        prompts: Shorthand for text_prompts, creates PromptConfig internally.
        prompt_config: Full prompt configuration (overrides prompts).

        confidence_threshold: Minimum confidence for detections.
        min_mask_area: Minimum area (in pixels) for valid masks.
        max_mask_area: Maximum area (in pixels) for valid masks.

        video_mode: Enable video tracking with memory.
        output_masks: Include segmentation masks in output.
        output_labels: Include concept labels in output.

        imgsz: Image size for inference (width, height).

    Example (simple text prompts):
        SAM3DetectorConfig(prompts=["fish", "coral"])
    
    Example (hybrid with motion):
        SAM3DetectorConfig(
            prompt_config=PromptConfig(
                prompt_type=PromptType.DETECTOR,
                prompter=PrompterConfig(
                    detector_type="motion",
                    strategy=HybridStrategy.CLASSIFY_REGIONS,
                    text_prompts=["fish"],
                ),
            ),
        )
    
    Example (hybrid with YOLO):
        SAM3DetectorConfig(
            prompt_config=PromptConfig(
                prompt_type=PromptType.DETECTOR,
                prompter=PrompterConfig(
                    detector_type="yolo",
                    detector_config={"model": "yolov8n.pt"},
                    strategy=HybridStrategy.BOX_REFINEMENT,
                ),
            ),
        )
    """

    # Model settings
    checkpoint: str = "./models/sam3.pt"
    device: str = "cuda"
    half: bool = True
    
    # Prompting (simple)
    prompts: List[str] = field(default_factory=list)
    
    # Prompting (advanced)
    prompt_config: Optional[PromptConfig] = None
    
    # Detection filtering
    confidence_threshold: float = 0.25
    min_mask_area: int = 100
    max_mask_area: int = 1000000
    
    # Video settings
    video_mode: bool = True
    
    # Output options
    output_masks: bool = False
    output_labels: bool = True
    
    # Inference settings
    imgsz: int = 1024

    def __post_init__(self):
        """Build prompt config from simple prompts if needed."""

        # Only create PromptConfig if not already provided
        if self.prompt_config is None:
            if self.prompts:
                # User provided simple prompts - create TEXT config
                self.prompt_config = PromptConfig(
                    prompt_type=PromptType.TEXT,
                    text_prompts=self.prompts,
                )
            # If no prompts and no prompt_config, leave as None
            # Detector will validate at runtime when process_frame is called

        # Warn if cpu andFP16 used
        if self.device == "cpu" and self.half:
            logger.warning("FP16 (half=True) is not supported on CPU. Setting half=False.")
            self.half = False

    def get_ultralytics_overrides(self) -> Dict:
        """Get config dict for Ultralytics predictors."""
        return {
            "conf": self.confidence_threshold,
            "task": "segment",
            "mode": "predict",
            "model": self.checkpoint,
            "half": self.half,
            "imgsz": self.imgsz,
            "device": self.device,
            "verbose": False,
        }
