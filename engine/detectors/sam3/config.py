"""
Configuration classes for the SAM3 detector with Ultralytics integration.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Union


class PromptType(Enum):
    """
    Types of prompts to use for SAM3 segmentation.
    """

    TEXT = auto()      # Text concepts
    BOX = auto()       # Bounding box exemplars
    POINT = auto()     # Point prompts (SAM2 style)
    DETECTOR = auto()  # Use another deterctor to generate prompts


class HybridStrategy(Enum):
    """How to use detector outputs with SAM3."""

    BOX_REFINEMENT= auto()
    CLASSIFY_REGIONS = auto()


@dataclass
class PrompterConfig:
    """
    Configuration for the prompt source in hybrid/detector mode.

    In hybrid mode, another detector geberates candidate boxes that become
    prompts for SAM3. This allows combining fast detector (motion/YOLO) with
    SAM3'3 segementation and semantic understanding.

    Attributes:
        detector_type: Type of detector to use ("motion", "yolo" or custom)
        detector_config: Configuration dict passed to the detector.
        strategy: How to combine detector output with SAM3.
        text_prompts: Text prompts for CLASSIFY_REGIONS strategy.
        min_iou_with_prompt: Minimum IoU between SAM3 output and original
            detector box to keep the detection (filters false positives).

    Example (motion + SAM 3 refinement):
        PrompterConfig(
            detector_type="motion",
            detector_config={"min_area": 200, "persistence_enabled": True},
            strategy=HybridStrategy.BOX_REFINEMENT,
        )
    
    Example (motion finds candidates, SAM 3 classifies):
        PrompterConfig(
            detector_type="motion",
            detector_config={"min_area": 100},
            strategy=HybridStrategy.CLASSIFY_REGIONS,
            text_prompts=["fish", "coral", "debris"],  # What to look for
        )
    
    Example (YOLO + SAM 3 masks):
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

    SAM3 support multiple prompt types:
    - Text: find all instances of concepts (e.g. fish, "seal")
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

        # For Detector mode (hybrid):
        prompter: Configuration for the prompt-generating detector.

        # Video settings
        reprompt_interval: Interval (in frames) to re-generate prompts in video.
            For frame sbetween prompts, only existing objects are tracked. This
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
        
        prompts: shorthand for text_prompts, creates PromptConfig internally
        prompt_config: Full prompt configuration (ovverrides prompts).

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
    checkpoint: str = "./models/sam3.pt" # Default when run locally with sam3.pt checkpoint downloaded to ./models/
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

        if self.prompt_config is None:
            if self.prompts:
                self.prompt_config = PromptConfig(
                    prompt_type=PromptType.TEXT,
                    text_prompts=self.prompts,
                )
            else:
                # Empty config - must be set before use
                self.prompt_config = PromptConfig(
                    prompt_type=PromptType.TEXT,
                    text_prompts=[],
                )

    
    def get_ultralytics_overrides(self) -> Dict:
        """Get config dict for Ultralytics predictors."""
        return {
            "conf": self.confidence_threshold,
            "task": "segment",
            "mode": "predict",
            "model": self.checkpoint,
            "half": self.half,
            "imgsz": self.imgsz,
            "verbose": False,
        }