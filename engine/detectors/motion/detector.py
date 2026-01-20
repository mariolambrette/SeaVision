"""Motion detector combining stabilisation and background modelling."""

from dataclasses import dataclass, field
from typing import Dict, Iterator, Optional, Tuple
import cv2
import numpy as np

from engine.source import FrameContext
from engine.detectors.base import Detection, DetectorBase
from .stabiliser import FrameStabiliser, StabiliserConfig
from .background import BackgroundModel, BackgroundConfig


@dataclass
class MotionDetectorConfig:
    """
    Configuration for the motion detector.
    
    Attributes:
        stabiliser: Configuration for the frame stabiliser.
        background: Confiuguration for the background subtraction.
        stabilisation_enabled: Whether to enable frame stabilisation.
        min_area: Minimum area (pixels) for motion contours to be considered.
        max_area: Maximum area (pixels) for motion contours to be considered.
        morph_kernel_size: Kernel size for morphological operations.
        morph_iterations: Number of iterations for morphological operations.
    """

    stabiliser: StabiliserConfig = field(
        default_factory=StabiliserConfig
    )
    background: BackgroundConfig = field(
        default_factory=BackgroundConfig
    )
    stabilisation_enabled: bool = True
    min_area: int = 100  # pixels
    max_area: int = 50000  # pixels
    morph_kernel_size: int = 5
    morph_iterations: int = 2

    # Persistence filtering
    persistence_enabled: bool = True
    min_persistence: int = 3      # Frames before emitting detection
    max_frames_missing: int = 5   # Frames before dropping track
    iou_threshold: float = 0.3    # Minimum IoU to match detections


class MotionDetector(DetectorBase):
    """
    Detects motion in video frames using background subtraction in the
    following pipeline:
        1. (Optional) Stabilise frame to compensate for camera motion.
        2. Apply background subtraction to get a foreground mask.
        3. Clean mask with morphological operations.
        4. Find countours and filter by area.
        5. Emit Detection objects for valid contours.

    Example:
        config = MotionDetectorConfig(min_area=200)

        with MotionDetector(config) as detector:
            for frame, context in video_source.iter_frames():
                for detection in detector.process_frame(frame, context):
                    # process detection
                    pass
    """

    def __init__(self, config: Optional[MotionDetectorConfig] = None):
        """
        Initialise the motion detector.

        Args:
            config: Configuration for the motion detector. If None, defaults
                are used.
        """

        self.config = config or MotionDetectorConfig()

        self._stabiliser = FrameStabiliser(self.config.stabiliser)
        self._background = BackgroundModel(self.config.background)

        # Morphological operation kernel
        self._morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (self.config.morph_kernel_size, self.config.morph_kernel_size)
        )

        # Persistence tracker
        if self.config.persistence_enabled:
            from .tracker import PersistenceTracker, TrackerConfig
            tracker_config = TrackerConfig(
                min_persistence=self.config.min_persistence,
                max_frames_missing=self.config.max_frames_missing,
                iou_threshold=self.config.iou_threshold
            )
            self._tracker = PersistenceTracker(tracker_config)
        else:
            self._tracker = None

    
    def process_frame(
        self,
        frame: np.ndarray,
        context: FrameContext
    ) -> Iterator[Detection]:
        """
        Process a single video frame and yield motion detections.

        Args:
            frame: BGR image as a numpy array (H x W x 3).
            context: Metadata about the current frame (FrameContext class).
        
        Yields:
            Detection objects for each motion contour found in the frame.
        """

        # Stage 1: Stabilisation
        if self.config.stabilisation_enabled:
            stabilised, _ = self._stabiliser.stabilise(frame)
        else:
            stabilised = frame

        # Stage 2: Background subtraction
        mask = self._background.apply(stabilised)

        # Stage 3: Morphological cleaning
        mask = self._clean_mask(mask)

        # Stage 4: Extract raw detections
        raw_detections = list(self._extract_detections(mask, context))

        # Stage 5: Persistence filtering
        if self._tracker is not None:
            confirmed_tracks = self._tracker.update(raw_detections)

            for track in confirmed_tracks:
                yield Detection(
                    source_file=context.source_file,
                    timestamp=context.timestamp,
                    frame_number=context.frame_number,
                    xc=track.xc,
                    yc=track.yc,
                    width=track.width,
                    height=track.height,
                    confidence=None  # No confidence score for motion detection
                )
        else:
            # No tracking - emit all detections
            for det in raw_detections:
                yield Detection(
                    source_file=context.source_file,
                    timestamp=context.timestamp,
                    frame_number=context.frame_number,
                    **det
                )
    
    def _clean_mask(self, mask: np.ndarray) -> np.ndarray:
        """
        Apply morphological operations to clean the foreground mask.
        """

        # Opening (erosion then dilation) removes small noise
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            self._morph_kernel,
            iterations=self.config.morph_iterations
        )

        # Closing (dilation then erosion) fills small holes
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            self._morph_kernel,
            iterations=self.config.morph_iterations
        )

        return mask
    

    def _extract_detections(
        self,
        mask: np.ndarray,
        context: FrameContext
    ) -> Iterator[Dict]:
        """
        Find contours in the mask and yield Detection dicts (for tracker input).
        """

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        for contour in contours:
            area = cv2.contourArea(contour)

            # Filter by size
            if area < self.config.min_area or area > self.config.max_area:
                continue

            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)
            
            yield {
                "xc": x + w / 2,
                "yc": y + h / 2,
                "width": w,
                "height": h,
            }
    
    def reset(self) -> None:
        """Reset internal state between videos."""
        self._stabiliser.reset()
        self._background.reset()
        if self._tracker is not None:
            self._tracker.reset()
