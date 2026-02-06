"""Pipeline orchestration for buoy detection system."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Type, Union

from tqdm import tqdm

from engine import (
    VideoSource,
    DetectionWriter,
    PostprocessorConfig,
    OutputMode,
    DetectorBase,
)
from engine.detectors.motion import(
    MotionDetectorConfig,
    MotionDetector,
    StabiliserConfig,
    BackgroundConfig
)
from engine.detectors.sam3 import(
    SAM3DetectorConfig,
    SAM3Detector,
)
from engine.visualiser import VisualiserConfig, LiveVisualiser

# Module logger
logger = logging.getLogger(__name__)

# ==============================================================================
# DETECTOR REGISTRY
# ==============================================================================

# Type alias for detector classes
DetectorClass = Type[DetectorBase]
ConfigParser = Callable[[dict], object]

# Registry mapping detector type names to (DetectorClass, config_parser) tuples
# Config parser takes a dict and returns the appropiate config object
DETECTOR_REGISTRY: Dict[str, Tuple[DetectorClass, ConfigParser]] = {}

def register_detector(
    name: str,
    detector_class: DetectorClass,
    config_parser: ConfigParser
) -> None:
    """
    Register a detector type for use with YAML configuration.

    Args:
        name: Name used in config files (e.g., "motion", "yolo").
        detector_class: The detector class.
        config_parser: Function that parses a config dict into the appropriate
            config object for this detector.
    """
    DETECTOR_REGISTRY[name] = (detector_class, config_parser) 
    logger.debug(f"Registered detector '{name}'.")

def _parse_motion_config(data:dict) -> MotionDetectorConfig:
    """
    Parse a dictionary into MotionDetectorConfig.
    """
    # Stabiliser sub-config
    stabiliser_data = data.get("stabiliser", {})
    stabiliser = StabiliserConfig(
        feature_detector=stabiliser_data.get("feature_detector", "ORB"),
        max_features=stabiliser_data.get("max_features", 500),
        match_ratio=stabiliser_data.get("match_ratio", 0.75),
        min_matches=stabiliser_data.get("min_matches", 10),
        ransac_threshold=stabiliser_data.get("ransac_threshold", 5.0),
    )

    # Background sub-config
    background_data = data.get("background", {})
    background = BackgroundConfig(
        history=background_data.get("history", 600),
        var_threshold=background_data.get("var_threshold", 16),
        detect_shadows=background_data.get("detect_shadows", True),
        learning_rate=background_data.get("learning_rate", -1)
    )

    # Main motion detector config
    return MotionDetectorConfig(
        stabiliser=stabiliser,
        background=background,
        stabilisation_enabled=data.get("stabilisation_enabled", True),
        min_area=data.get("min_area", 500),
        max_area=data.get("max_area", 5000),
        morph_kernel_size=data.get("morph_kernel_size", 5),
        morph_iterations=data.get("morph_iterations", 2),
        # Persistence filtering
        persistence_enabled=data.get("persistence_enabled", True),
        min_persistence=data.get("min_persistence", 3),
        max_frames_missing=data.get("max_frames_missing", 5),
        iou_threshold=data.get("iou_threshold", 0.3),
    )

# Register built-in detectors
register_detector(
    "motion",
    MotionDetector,
    _parse_motion_config
)

def _parse_sam3_config(data: dict) -> "SAM3DetectorConfig":
    """Parse a dictionary into SAM3DetectorConfig."""
    from engine.detectors.sam3 import (
        SAM3DetectorConfig,
        PromptConfig,
        PromptType,
        PrompterConfig,
        HybridStrategy,
    )
    
    # Handle simple prompts shorthand
    prompts = data.get("prompts", [])
    
    # Handle advanced prompt_config
    prompt_config = None
    if "prompt_config" in data:
        pc_data = data["prompt_config"]
        
        # Parse prompt type
        prompt_type_str = pc_data.get("prompt_type", "TEXT").upper()
        prompt_type = PromptType[prompt_type_str]
        
        # Parse prompter config for DETECTOR mode
        prompter = None
        if "prompter" in pc_data:
            pr_data = pc_data["prompter"]
            strategy_str = pr_data.get("strategy", "BOX_REFINEMENT").upper()
            strategy = HybridStrategy[strategy_str]
            
            prompter = PrompterConfig(
                detector_type=pr_data.get("detector_type", "motion"),
                detector_config=pr_data.get("detector_config", {}),
                strategy=strategy,
                text_prompts=pr_data.get("text_prompts", []),
                min_iou_with_prompt=pr_data.get("min_iou_with_prompt", 0.0),
            )
        
        prompt_config = PromptConfig(
            prompt_type=prompt_type,
            text_prompts=pc_data.get("text_prompts", []),
            box_prompts=pc_data.get("box_prompts", []),
            box_labels=pc_data.get("box_labels", []),
            point_prompts=pc_data.get("point_prompts", []),
            point_labels=pc_data.get("point_labels", []),
            prompter=prompter,
            reprompt_interval=pc_data.get("reprompt_interval", 0),
            reprompt_on_lost=pc_data.get("reprompt_on_lost", True),
        )
    
    return SAM3DetectorConfig(
        checkpoint=data.get("checkpoint", "sam3.pt"),
        device=data.get("device", "cuda"),
        half=data.get("half", True),
        prompts=prompts,
        prompt_config=prompt_config,
        confidence_threshold=data.get("confidence_threshold", 0.25),
        min_mask_area=data.get("min_mask_area", 100),
        max_mask_area=data.get("max_mask_area", 1000000),
        video_mode=data.get("video_mode", True),
        output_masks=data.get("output_masks", False),
        output_labels=data.get("output_labels", True),
        imgsz=data.get("imgsz", 1024),
    )


# Register SAM 3 detector (conditional on availability)
try:
    from engine.detectors.sam3 import SAM3Detector
    register_detector("sam3", SAM3Detector, _parse_sam3_config)
except ImportError:
    logger.debug("SAM 3 detector not available (ultralytics not installed)")

# ==============================================================================
# CONFIGURATION DATACLASSES
# ==============================================================================

@dataclass
class InputConfig:
    """
    Configuration for pipeline input processing.

    Note: Video discovery (paths, patterns) is handled externally via
    discover_local_videos() or discover_s3_videos(). This config only
    contains processing options.

    Attributes:
        frame_skip: Process every Nth frame (1 = all frames, 5 = every 5th).
    """

    frame_skip: int = 1


@dataclass
class DetectorConfig:
    """
    Configuration for detector selection and settings.
    
    Attributes:
        type: Detector type name (must be registered in DETECTOR_REGISTRY).
        config: Dictionary of detector-specific configuration options.
    """
    type: str = "motion"
    config: dict = field(default_factory=dict)    


@dataclass
class PipelineConfig:
    """
    Configuration for the pipeline input.

    Attributes:
        input: Input file/directory configuration.
        output: Output/postprocessing configuration.
        detector: Detector configuration
        resume: If True, skip videos that already have output files.
    """

    input: InputConfig = field(default_factory=InputConfig)
    output: PostprocessorConfig = field(default_factory=PostprocessorConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    resume: bool = True
    visualiser: Optional[VisualiserConfig] = None

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineConfig":
        """
        Create a PipelineConfig from a dictionary (e.g. loaded from YAML).

        Args:
            data: Dictionary containing configuration data.
        
        Returns:
            PipelineConfig instance.
        """

        # Parse input config
        input_data = data.get("input", {})
        input_config = InputConfig(
            frame_skip=input_data.get("frame_skip", 1),
        )

        # Parse output config
        output_data = data.get("output", {})
        output_mode_str = output_data.get("output_mode", "per_video")
        output_mode = (
            OutputMode.SINGLE_FILE if output_mode_str == "single"
            else OutputMode.PER_VIDEO
        )
        output_config = PostprocessorConfig(
            output_dir=output_data.get("directory", "./output"),
            output_mode=output_mode,
            single_file_name=output_data.get("single_file_name", "detections.csv"),
            overwrite=output_data.get("overwrite", False)
        )

        # Parse detector config (Generic)
        detector_data = data.get("detector", {})
        detector_config = DetectorConfig(
            type=detector_data.get("type", "motion"),
            config=detector_data.get("config", {})
        )

        # Top level options
        resume = data.get("resume", False)

        return cls(
            input=input_config,
            output=output_config,
            detector=detector_config,
            resume=resume
        )

# ==============================================================================
# RESULT CLASSES
# ==============================================================================

@dataclass
class DryRunResult:
    """
    Results from a dry run.

    Attributes:
        videos_found: Number of video files found.
        videos_to_process: Number of videos that would be processed.
        videos_skipped: Number of videos that would be skipped (already have output).
        total_frames: Total number of frames across all videos.
        total_duration: Total duration of all videos (seconds).
        output_mode: Output mode that would be used.
        output_dir: Directory where output would be saved.
    """

    videos_found: int = 0
    videos_to_process: int = 0
    videos_skipped: int = 0
    total_frames: int = 0
    total_duration: float = 0.0
    output_mode: str = ""
    output_dir: str = ""

    def summary(self) -> str:
        """Generate a human readable summary."""

        hours = int(self.total_duration // 3600)
        minutes = int((self.total_duration % 3600) // 60)

        lines = [
            "Dry run complete:",
            f"  Videos found: {self.videos_found}",
            f"  Videos to process: {self.videos_to_process}"
        ]

        if self.videos_skipped > 0:
            lines.append(f"  Videos to skip (resume): {self.videos_skipped}")

        lines.extend([
            f"  Total frames: {self.total_frames}",
            f"  Total duration: {hours}h {minutes}m",
            f"  Output mode: {self.output_mode}",
            f"  Output directory: {self.output_dir}"
        ])

        return "\n".join(lines)
    

@dataclass
class PipelineResult:
    """
    Results from a pipeline run.

    Attributes:
        videos_processed: Number of videos successfuly processed.
        videos_skipped: Number of videos skipped (resume mode).
        videos_failed: Number of videos that failed processing.
        total_detections: Total number of detections across all videos.
        elapsed_time: Total elapsed time (seconds).
        detections_per_video: DIctionary mapping video path to number of detections.
        failed_videos: Dictionary mapping video path to error message.
    """

    videos_processed: int = 0
    videos_skipped: int = 0
    videos_failed: int = 0
    total_detections: int = 0
    elapsed_time: float = 0.0
    detections_per_video: Dict = field(default_factory=dict)
    failed_videos: Dict = field(default_factory=dict)

    def summary(self) -> str:
        """Generate a human readable summary."""

        lines = [
            "Pipeline Results:",
            f"  Videos processed: {self.videos_processed}",
        ]

        if self.videos_skipped > 0:
            lines.append(f"  Videos skipped (resume): {self.videos_skipped}")

        lines.extend([
            f"  Videos failed: {self.videos_failed}",
            f"  Total detections: {self.total_detections}",
            f"  Elapsed time: {self.elapsed_time:.1f} seconds"
        ])

        if self.failed_videos:
            lines.append("  Failed videos:")
            for video, error in self.failed_videos.items():
                lines.append(f"    - {Path(video).name}: {error}")
        
        return "\n".join(lines)
    

# ==============================================================================
# PIPELINE CLASS
# ==============================================================================

class DetectionPipeline:
    """
    Main pipeline for processing videos and detecting objects.

    Ochestrates video loading, detection, and output writing.
    Supports pluggable detectors via factory function or a registry.

    Example (default motion detector):
        config = PipelineConfig(
            input=InputConfig(path="./footage/"),
            output=PostprocessorConfig(output_dir="./results"),
        )
        
        pipeline = Pipeline(config)
        result = pipeline.run()
        print(result.summary())
    
    Example (custom detector via factory):
        pipeline = Pipeline(
            config,
            detector_factory=lambda: MotionDetector(
                MotionDetectorConfig(min_area=500)
            )
        )
        result = pipeline.run()
    
    Example (future ML detector):
        pipeline = Pipeline(
            config,
            detector_factory=lambda: YOLODetector(model_path="weights/fish.pt")
        )
    
    Example (via YAML config):
        # config.yaml:
        # detector:
        #   type: motion
        #   config:
        #     min_area: 500
        
        config = PipelineConfig.from_dict(yaml.safe_load(open("config.yaml")))
        pipeline = Pipeline(config)
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        detector_factory: Optional[Callable[[], DetectorBase]] = None
    ):
        """
        Initialise the detection pipeline.

        Args:
            config: Pipeline configuration. If None, defaults are used.
            detector_factory: Optional callable that returns a new detector
                instance. If provided, overrides the detector config from
                PipelineConfig. Use this for maximum flexibility when configuring
                detectors programmatically.
        """

        self.config = config or PipelineConfig()
        self._detector_factory = detector_factory or self._create_detector_from_config

        # Create visualiser if configured
        self._visualiser: Optional[LiveVisualiser] = None
        if self.config.visualiser is not None:
            self._visualiser = LiveVisualiser(self.config.visualiser)

        logger.info("DetectionPipeline initialised.")
        logger.debug(f"Output directory: {self.config.output.output_dir}")
        logger.debug(f"Detector type: {self.config.detector.type}")

        if self.config.input.frame_skip > 1:
            logger.info(
                f"Frame skipping enabled: processing every "
                f"{self.config.input.frame_skip} frame(s)."
            )
        
        if self.config.resume:
            logger.info("Resume mode enabled: skipping videos with exisiting outputs.")

        if self._visualiser is not None:
            logger.info("Live visualiser enabled.")

    
    def _create_detector_from_config(self) -> DetectorBase:
        """
        Creates a detector instance based on the pipeline config.

        Uses the detector registry to look up the appropiate class and config
        parser.

        Returns:
            A new detector instance.

        Raises:
            ValueError: If the specified detector type is not registered.
        """

        detector_type = self.config.detector.type

        if detector_type not in DETECTOR_REGISTRY:
            available = list(DETECTOR_REGISTRY.keys())
            raise ValueError(
                f"Unknown detector type '{detector_type}'. "
                f"Available types: {available}"
                f"Add new detectors via register_detector()."
            )

        detector_class, config_parser = DETECTOR_REGISTRY[detector_type]
        detector_config = config_parser(self.config.detector.config)

        return detector_class(detector_config)
    

    def process_sources(
        self,
        sources: List[VideoSource],
        dry_run: bool = False,
    ) -> Union[PipelineResult, DryRunResult]:
        """
        Process a list of video sources.

        This is the main entry point. Sources can come from any discovery
        function (discover_local_videos, discover_s3_videos, etc.).

        Args:
            sources: List of VideoSource instances to process.
            dry_run: If True, gather statistics without actually processing.

        Returns:
            PipelineResult with processing statistics, or DryRunResult if
            dry_run is True.

        Example:
            from engine import discover_local_videos

            sources = discover_local_videos("./footage/", "*.ts")
            result = pipeline.process_sources(sources)
        """
        if not sources:
            logger.warning("No video sources provided.")
            if dry_run:
                return DryRunResult()
            return PipelineResult()

        logger.info(f"Processing {len(sources)} video source(s).")

        if dry_run:
            return self._dry_run(sources)
        else:
            return self._process_sources(sources)
        
    
    def _get_source_identifier(self, source: VideoSource) -> str:
        """
        Get a unique identifier for a video source.

        Uses the source_file from metadata, which is set during source
        creation.

        Args:
            source: VideoSource instance.

        Returns:
            String identifier (typically the file path or URI).
        """
        metadata = source.get_metadata()
        return metadata.source_file

    def _get_output_path(self, source_identifier: str) -> Path:
        """
        Get the output CSV file path for a given source.

        Args:
            source_identifier: Unique identifier for the source.

        Returns:
            Path to the output CSV file.
        """
        if self.config.output.output_mode == OutputMode.SINGLE_FILE:
            return (
                Path(self.config.output.output_dir)
                / self.config.output.single_file_name
            )
        else:
            # Extract stem from identifier (works for paths and URIs)
            name = Path(source_identifier).stem
            return (
                Path(self.config.output.output_dir)
                / f"{name}_detections.csv"
            )
        
    
    def _should_skip_source(self, source: VideoSource) -> bool:
        """
        Determine whether to skip processing a source based on resume mode.

        Args:
            source: VideoSource instance.

        Returns:
            True if the source should be skipped, False otherwise.
        """
        if not self.config.resume:
            return False

        # Can't resume in single file mode (would need to parse existing CSV)
        if self.config.output.output_mode == OutputMode.SINGLE_FILE:
            return False

        source_id = self._get_source_identifier(source)
        output_path = self._get_output_path(source_id)
        return output_path.exists()
    

    def _dry_run(self, sources: List[VideoSource]) -> DryRunResult:
        """
        Perform a dry run - gather statistics without processing.

        Args:
            sources: List of VideoSource instances to scan.

        Returns:
            DryRunResult with gathered statistics.
        """
        result = DryRunResult(
            videos_found=len(sources),
            output_mode=self.config.output.output_mode.value,
            output_dir=self.config.output.output_dir,
        )

        sources_to_process = []

        for source in tqdm(sources, desc="Scanning videos", unit="video"):
            if self._should_skip_source(source):
                result.videos_skipped += 1
                continue

            sources_to_process.append(source)

            # Get video metadata
            try:
                metadata = source.get_metadata()
                result.total_frames += metadata.frame_count
                result.total_duration += metadata.duration
            except Exception as e:
                source_id = self._get_source_identifier(source)
                logger.warning(
                    f"Could not read metadata from {source_id}: {e}"
                )

        result.videos_to_process = len(sources_to_process)

        # Adjust frame count for frame skipping
        if self.config.input.frame_skip > 1:
            result.total_frames = result.total_frames // self.config.input.frame_skip

        return result
    
    def _process_sources(self, sources: List[VideoSource]) -> PipelineResult:
        """
        Process a list of video sources.

        Args:
            sources: List of VideoSource instances to process.

        Returns:
            PipelineResult with processing statistics.
        """
        result = PipelineResult()
        start_time = time.time()

        with DetectionWriter(self.config.output) as writer:
            for source in tqdm(sources, desc="Processing videos", unit="video"):
                # Get source identifier for logging and output
                source_id = self._get_source_identifier(source)
                source_name = Path(source_id).name

                # Check if we should skip this source (resume mode)
                if self._should_skip_source(source):
                    logger.debug(f"Skipping (resume): {source_name}")
                    result.videos_skipped += 1
                    continue

                try:
                    detection_count = self._process_single_source(source, writer)
                    result.detections_per_video[source_id] = detection_count
                    result.videos_processed += 1

                    # Finalise to handle empty videos
                    writer.finalise_video(source_id)

                except Exception as e:
                    logger.error(f"Failed to process {source_name}: {e}")
                    result.failed_videos[source_id] = str(e)
                    result.videos_failed += 1
                    continue

        result.total_detections = writer.detection_count
        result.elapsed_time = time.time() - start_time

        # Log summary
        logger.info(
            f"Pipeline complete: {result.videos_processed} processed, "
            f"{result.videos_skipped} skipped, "
            f"{result.videos_failed} failed, "
            f"{result.total_detections} detections, "
            f"{result.elapsed_time:.1f}s elapsed."
        )

        if result.failed_videos:
            logger.warning(
                f"Failed videos: "
                f"{[Path(v).name for v in result.failed_videos.keys()]}"
            )

        return result


    def _process_single_source(
        self,
        source: VideoSource,
        writer: DetectionWriter,
    ) -> int:
        """
        Process a single video source.

        Args:
            source: VideoSource instance to process.
            writer: DetectionWriter instance for outputting detections.

        Returns:
            Number of detections made in this video.
        """
        source_id = self._get_source_identifier(source)
        source_name = Path(source_id).name
        logger.debug(f"Processing: {source_name}")

        detection_count = 0
        frame_skip = self.config.input.frame_skip

        metadata = source.get_metadata()
        logger.debug(
            f"Video: {metadata.frame_count} frames, "
            f"{metadata.duration:.1f}s, {metadata.fps:.1f} FPS"
        )

        # Start visualisation for this source
        if self._visualiser is not None:
            self._visualiser.start_video(metadata)
        
        try:
            with self._detector_factory() as detector:
                # Progress bar for frames
                frame_iter = tqdm(
                    source.iter_frames(),
                    desc=f"  {source_name}",
                    total=metadata.frame_count,
                    unit="frame",
                    leave=False,
                )

                for frame_idx, (frame, context) in enumerate(frame_iter):
                    # Skip frames if configured
                    if frame_skip > 1 and frame_idx % frame_skip != 0:
                        continue

                    # Collect frame detections
                    frame_detections = list(
                        detector.process_frame(frame, context)
                    )

                    # Write to CSV
                    for detection in frame_detections:
                        writer.write(detection)
                        detection_count += 1
                    
                    # Visualise frame with detections
                    if self._visualiser is not None:
                        self._visualiser.process_frame(
                            frame, frame_detections, context
                        )
        finally:
            # End visualisation for this source
            if self._visualiser is not None:
                vis_result = self._visualiser.end_video()
                logger.debug(f"Visualisation: {vis_result.summary()}")

        logger.debug(f"Completed {source_name}: {detection_count} detections.")
        return detection_count
    

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def setup_logging(level: int = logging.INFO) -> None:
    """
    Set up basic logging configuration.

    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG).
    """

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
