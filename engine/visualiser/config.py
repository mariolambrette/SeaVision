"""Configuration data classes for the visualiser module."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Tuple, Optional


class OutputMode(Enum):
    """Output mode for the visualiser."""
    FILE = auto()   # Write frames to video file
    STREAM = auto() # Yield frames for GUI integration
    BOTH = auto()   # Write frames to file and yield for GUI integration


class LabelPosition(Enum):
    """Position of label relative to bounding box."""
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()
    ABOVE = auto()
    BELOW = auto()


@dataclass
class BoundingBoxStyle:
    """Style configuration for bounding box rendering."""
    draw_box: bool = True
    colour: Tuple[int, int, int] = (0, 255, 0)  # BGR format green
    thickness: int = 2
    draw_centre: bool = False
    centre_radius: int = 3
    centre_colour: Tuple[int, int, int] = (0, 255, 0) # BGR format green


@dataclass
class LabelStyle:
    """Style configuration for label rendering."""
    enabled: bool = True
    font_scale: float = 0.5
    font_thickness: int = 1
    colour: Tuple[int, int, int] = (255, 255, 255)  # BGR format white
    background_colour: Optional[Tuple[int, int, int]] = (0, 0, 0)  # BGR format black
    position: LabelPosition = LabelPosition.TOP_LEFT
    padding: int = 2
    show_confidence: bool = True
    show_frame_number: bool = False
    custom_format: Optional[str] = None


@dataclass
class OverlayStyle:
    """Style configuration for frame-level overlay information"""
    enabled: bool = False
    show_frame_number: bool = True
    show_timestamp: bool = True
    show_detection_count: bool = True
    font_scale: float = 0.6
    font_thickness: int = 1
    colour: Tuple[int, int, int] = (255, 255, 255)
    background_colour: Optional[Tuple[int, int, int]] = (0, 0, 0)
    position: Tuple[int, int] = (10, 25)  # Top-left corner offset


@dataclass
class VideoOutputConfig:
    """
    Configuration for video file output.
    
    Attributes:
        output_dir: Directory where output videos will be saved.
        filename_suffix: Suffix added to the output filename stem
            (before the extension).
        codec: FourCC codec string for video encoding.
        format: Output file extension (including the dot).
        fps: Output frame rate. If None, matches source video.
        overwrite: If True, overwrite existing output files.
        include_parent_dirs: Number of parent directory levels to include
            in the output filename to avoid collisions. Only used when
            no custom name function is provided.
    """
    output_dir: str = "./visualised_output"
    filename_suffix: str = "_visualised"
    codec: str = "mp4v"
    format: str = ".mp4"
    fps: Optional[float] = None
    overwrite: bool = False
    include_parent_dirs: int = 2


@dataclass
class VisualiserConfig:
    """
    Main configuration for the visualiser module.

    Used by both LiveVisualiser (for pipeline integration) and PostHocVisualiser
    (CSV-based outputs).
    """

    output_mode: OutputMode = OutputMode.FILE
    video_output: VideoOutputConfig = field(
        default_factory=VideoOutputConfig
    )
    bbox_style: BoundingBoxStyle = field(
        default_factory=BoundingBoxStyle
    )
    label_style: LabelStyle = field(
        default_factory=LabelStyle
    )
    overlay_style: OverlayStyle = field(
        default_factory=OverlayStyle
    )

    # Filtering options
    min_confidence: Optional[float] = None  # Minimum confidence to visualise

    # Frame options - for post hoc mode
    only_frames_with_detections: bool = False  # Only visualise frames with detections
    frame_skip: int = 1

