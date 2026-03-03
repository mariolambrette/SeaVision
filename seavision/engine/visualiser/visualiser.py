"""High level visualiser orchestrators."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional
import numpy as np

from ..source.base import VideoSource, VideoMetadata, FrameContext
from ..detectors.base import Detection
from .config import VisualiserConfig, OutputMode
from .annotator import FrameAnnotator
from .writer import VideoWriterHandle, OutputNameFunction
from .loader import DetectionSource, CSVDetectionLoader


@dataclass
class AnnotatedFrame:
    """Container for an annotated frame (for streaming output)."""
    frame: np.ndarray
    frame_number: int
    timestamp: float
    detections: List[Detection]
    source_file: str


@dataclass
class VisualisationResult:
    """Result statistics from visualisation."""
    source_file: str
    output_path: Optional[str]
    total_frames: int
    frames_with_detections: int
    total_detections: int

    def summary(self) -> str:
        """Create a human readable output of validation results."""
        return (
            f"Visualised: {Path(self.source_file).name}\n"
            f"  Output: {self.output_path or '(stream only)'}\n"
            f"  Frames: {self.total_frames} "
            f"({self.frames_with_detections} with detections)\n"
            f"  Detections: {self.total_detections}"
        )


class LiveVisualiser:
    """
    Visualiser for integration with the detection pipeline.
    
    Designed to be called frame-by-frame as detections are generated,
    rather than loading detections from CSV post-hoc.
    
    Lifecycle:
        1. Create LiveVisualiser with config
        2. Call start_video() when beginning a new video
        3. Call process_frame() for each frame + its detections
        4. Call end_video() when finished with that video
    
    Example (pipeline integration):
        visualiser = LiveVisualiser(config)
        
        for source in sources:
            visualiser.start_video(source.get_metadata())
            
            for frame, context in source.iter_frames():
                detections = list(detector.process_frame(frame, context))
                annotated = visualiser.process_frame(frame, detections, context)
            
            result = visualiser.end_video()
            print(result.summary())
    
    Example (custom naming):
        def device_date_namer(meta: VideoMetadata) -> str:
            # Parse S3 URI to extract device and date
            parts = meta.source_file.split('/')
            device = parts[-4]  # e.g., "cam-3-0"
            date = parts[-2]    # e.g., "2025-01-15"
            stem = Path(meta.source_file).stem
            return f"{device}_{date}_{stem}"
        
        visualiser = LiveVisualiser(config, name_function=device_date_namer)
    """

    def __init__(
        self, 
        config: Optional[VisualiserConfig] = None,
        name_function: Optional[OutputNameFunction] = None
    ):
        """
        Initialise the live visualiser.

        Args:
            config: Visualisation configuration. If None, defaults are used.
            name_function: Optional custom function to generate output filenames.
                Takes VideoMetadata, returns the filename stem (without suffix
                or extension). If None, uses default naming based on source path.
        """
        self._config = config or VisualiserConfig()
        self._name_function = name_function
        self._annotator = FrameAnnotator(
            self._config.bbox_style,
            self._config.label_style,
            self._config.overlay_style,
        )
        
        # Per-video state
        self._writer: Optional[VideoWriterHandle] = None
        self._metadata: Optional[VideoMetadata] = None
        self._frames_processed: int = 0
        self._frames_with_detections: int = 0
        self._total_detections: int = 0

    def start_video(self, metadata: VideoMetadata) -> None:
        """
        Begin visualisation for a new video.
        
        Args:
            metadata: Metadata for the video being processed.
        
        Raises:
            RuntimeError: If called while another video is in progress.
        """

        if self._writer is not None:
            raise RuntimeError(
                "Previous video not ended. Call end_video() first."
            )
        
        self._metadata = metadata
        self._frames_processed = 0
        self._frames_with_detections = 0
        self._total_detections = 0

        # Open video writer if outputting to file
        if self._config.output_mode in (OutputMode.FILE, OutputMode.BOTH):
            self._writer = VideoWriterHandle(
                self._config.video_output,
                metadata,
                name_function=self._name_function
            )
    
    def process_frame(
        self, frame: np.ndarray,
        detections: List[Detection],
        context: FrameContext
    ) -> Optional[AnnotatedFrame]:
        """
        Process a single frame with its detections.
        
        Args:
            frame: BGR image as numpy array
            detections: List of detections for this frame
            context: Frame context with metadata

        Returns:
            AnnotatedFrame if output_mode includes STREAM, else None.
        
        Raises:
            RuntimeError: If called when no video is in progress.
        """

        if self._metadata is None:
            raise RuntimeError(
                "No video in progress. Call start_video() first."
            )
        
        # Apply confidence filter
        if self._config.min_confidence is not None:
            detections = [
                d for d in detections
                if d.confidence is None
                or d.confidence >= self._config.min_confidence
            ]

        # Skip frames without detections if configured
        if self._config.only_frames_with_detections and not detections:
            return None
        
        # Update statistics
        self._frames_processed += 1
        self._total_detections += len(detections)
        if detections:
            self._frames_with_detections += 1

        # Annotate frame
        annotated = self._annotator.annotate_frame(
            frame, detections, context, copy=True
        )

        # Write to video file if configured
        if self._writer is not None:
            self._writer.write(annotated)
        
        # Return for streaming if configured
        if self._config.output_mode in (OutputMode.STREAM, OutputMode.BOTH):
            return AnnotatedFrame(
                frame=annotated,
                frame_number=context.frame_number,
                timestamp=context.timestamp,
                detections=detections,
                source_file=self._metadata.source_file
            )

        return None
    
    def end_video(self) -> VisualisationResult:
        """
        Finish visualisation for the current video.
        
        Returns:
            VisualisationResult with summary statistics.
        
        Raises:
            RuntimeError: If called when no video is in progress.
        """

        if self._metadata is None:
            raise RuntimeError("No video in progress")

        # Close video writer
        output_path = None
        if self._writer is not None:
            output_path = str(self._writer.output_path)
            self._writer.close()
            self._writer = None

        result = VisualisationResult(
            source_file=self._metadata.source_file,
            output_path=output_path,
            total_frames=self._frames_processed,
            frames_with_detections=self._frames_with_detections,
            total_detections=self._total_detections,
        )

        # Reset state
        self._metadata = None

        return result
    

    def __enter__(self) -> "LiveVisualiser":
        return self
    
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # Clean up if video was not properly ended
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        return False


class PostHocVisualiser:
    """
    Visualiser for post-hoc processing from CSV detection files.
    
    Reads detections from CSV and overlays them on the source video.
    
    Example:
        visualiser = PostHocVisualiser(config)
        
        with LocalVideoSource("footage/video.ts") as source:
            result = visualiser.visualise(source, "results/video_detections.csv")
            print(result.summary())
    
    Example (custom naming):
        def custom_namer(meta: VideoMetadata) -> str:
            return f"reviewed_{Path(meta.source_file).stem}"
        
        visualiser = PostHocVisualiser(config, name_function=custom_namer)
    """

    def __init__(
        self, 
        config: Optional[VisualiserConfig] = None,
        name_function: Optional[OutputNameFunction] = None
    ):
        self._config = config or VisualiserConfig()
        self._name_function = name_function
        self._annotator = FrameAnnotator(
            self._config.bbox_style,
            self._config.label_style,
            self._config.overlay_style,
        )


    def visualise(
        self,
        video_source: VideoSource,
        csv_path: str,
    ) -> Iterator[AnnotatedFrame]:
        """
        Visualise a video using detections from a CSV file.

        Args:
            video_source: VideoSource to read frames from.
            csv_path: Path to CSV file with detections.
        
        Yields:
            AnnotatedFrame objects if output_mode includes STREAM.
        """

        detection_source = CSVDetectionLoader(
            csv_path,
            source_file=video_source.get_metadata().source_file
        )
        yield from self._visualise(video_source, detection_source)


    def visualise_from_source(
            self,
            video_source: VideoSource,
            detection_source: DetectionSource,
    ) -> Iterator[AnnotatedFrame]:
        """
        Visualise a video using a detection source.

        Args:
            video_source: VideoSource to read frames from.
            detection_source: DetectionSource to provide detections.
        
        Yields:
            AnnotatedFrame objects if output_mode includes STREAM.
        """
        yield from self._visualise(video_source, detection_source)

    
    def _visualise(
        self,
        video_source: VideoSource,
        detection_source: DetectionSource,
    ) -> Iterator[AnnotatedFrame]:
        """Core visualisation loop for post-hoc mode."""

        metadata = video_source.get_metadata()
        writer = None

        # Statistics
        frames_processed = 0
        frames_with_detections = 0
        total_detections = 0

        if self._config.output_mode in (OutputMode.FILE, OutputMode.BOTH):
            writer = VideoWriterHandle(
                self._config.video_output,
                metadata,
                name_function=self._name_function
            )

        try:
            for frame, context in video_source.iter_frames():
                # Frame skipping
                if context.frame_number % self._config.frame_skip != 0:
                    continue
                    
                # Get detections for this frame
                detections = detection_source.get_detections_for_frame(
                    context.frame_number
                )

                # Apply confidence filter
                if self._config.min_confidence is not None:
                    detections = [
                        d for d in detections
                        if d.confidence is None
                        or d.confidence >= self._config.min_confidence
                    ]

                # Skip frames without detections if configured
                if self._config.only_frames_with_detections and not detections:
                    continue

                # Update statistics
                frames_processed += 1
                if detections:
                    frames_with_detections += 1
                    total_detections += len(detections)

                # Annotate frame
                annotated = self._annotator.annotate_frame(
                    frame, detections, context
                )

                # Write to file
                if writer is not None:
                    writer.write(annotated)

                # Yield for streaming
                if self._config.output_mode in (OutputMode.STREAM, OutputMode.BOTH):
                    yield AnnotatedFrame(
                        frame=annotated,
                        frame_number=context.frame_number,
                        timestamp=context.timestamp,
                        detections=detections,
                        source_file=metadata.source_file
                    )
        finally:
            if writer is not None:
                writer.close()
                


