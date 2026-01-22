# SeaVision API Reference

Complete API documentation for all classes, functions, and data structures in the SeaVision package.

---

## Table of Contents

- [Video Sources](#video-sources)
  - [VideoMetadata](#videometadata)
  - [FrameContext](#framecontext)
  - [VideoSource](#videosource)
  - [LocalVideoSource](#localvideosource)
  - [S3VideoSource](#s3videosource)
- [Discovery Functions](#discovery-functions)
  - [discover_local_videos](#discover_local_videos)
  - [discover_s3_videos](#discover_s3_videos)
- [Detectors](#detectors)
  - [Detection](#detection)
  - [DetectorBase](#detectorbase)
  - [MotionDetector](#motiondetector)
  - [MotionDetectorConfig](#motiondetectorconfig)
- [Motion Detection Components](#motion-detection-components)
  - [FrameStabiliser](#framestabiliser)
  - [StabiliserConfig](#stabiliserconfig)
  - [BackgroundModel](#backgroundmodel)
  - [BackgroundConfig](#backgroundconfig)
  - [PersistenceTracker](#persistencetracker)
  - [TrackerConfig](#trackerconfig)
  - [TrackedObject](#trackedobject)
- [Postprocessor](#postprocessor)
  - [DetectionWriter](#detectionwriter)
  - [PostprocessorConfig](#postprocessorconfig)
  - [OutputMode](#outputmode-postprocessor)
- [Visualiser](#visualiser)
  - [LiveVisualiser](#livevisualiser)
  - [PostHocVisualiser](#posthocvisualiser)
  - [FrameAnnotator](#frameannotator)
  - [VideoWriterHandle](#videowriterhandle)
  - [AnnotatedFrame](#annotatedframe)
  - [VisualisationResult](#visualisationresult)
- [Visualiser Configuration](#visualiser-configuration)
  - [VisualiserConfig](#visualiserconfig)
  - [VideoOutputConfig](#videooutputconfig)
  - [BoundingBoxStyle](#boundingboxstyle)
  - [LabelStyle](#labelstyle)
  - [OverlayStyle](#overlaystyle)
  - [OutputMode](#outputmode-visualiser)
  - [LabelPosition](#labelposition)
- [Detection Loaders](#detection-loaders)
  - [DetectionSource](#detectionsource)
  - [CSVDetectionLoader](#csvdetectionloader)
  - [FrameDetections](#framedetections)
  - [IteratorDetectionSource](#iteratordetectionsource)
  - [ListDetectionSource](#listdetectionsource)
- [Pipeline](#pipeline)
  - [DetectionPipeline](#detectionpipeline)
  - [PipelineConfig](#pipelineconfig)
  - [InputConfig](#inputconfig)
  - [DetectorConfig](#detectorconfig)
  - [PipelineResult](#pipelineresult)
  - [DryRunResult](#dryrunresult)
- [Utility Functions](#utility-functions)

---

## Video Sources

### VideoMetadata

```python
from engine.source import VideoMetadata
```

**Module:** `engine.source.base`

**Type:** `dataclass`

Container for video file metadata properties.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_file` | `str` | Path or URI of the original source file |
| `fps` | `float` | Frames per second of the video |
| `frame_count` | `int` | Total number of frames in the video |
| `width` | `int` | Width of the video frames in pixels |
| `height` | `int` | Height of the video frames in pixels |
| `duration` | `float` | Duration of the video in seconds |

---

### FrameContext

```python
from engine.source import FrameContext
```

**Module:** `engine.source.base`

**Type:** `dataclass`

Context information passed with each frame to detectors.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_file` | `str` | Path or identifier of the source video |
| `frame_number` | `int` | Frame index within the video (0-indexed) |
| `timestamp` | `float` | Timestamp within the video in seconds from start |
| `fps` | `float` | Frames per second of the source video |

---

### VideoSource

```python
from engine.source import VideoSource
```

**Module:** `engine.source.base`

**Type:** `ABC` (Abstract Base Class)

Abstract base class for video sources. Provides a common interface for loading video frames from different backends.

#### Abstract Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `iter_frames()` | None | `Iterator[Tuple[np.ndarray, FrameContext]]` | Iterate over frames yielding (frame, context) tuples |
| `get_metadata()` | None | `VideoMetadata` | Get metadata about the video source |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `close()` | None | `None` | Release any resources held by the source |
| `__enter__()` | None | `VideoSource` | Context manager entry |
| `__exit__()` | exc_type, exc_val, exc_tb | `bool` | Context manager exit with cleanup |

---

### LocalVideoSource

```python
from engine.source import LocalVideoSource
```

**Module:** `engine.source.local`

**Type:** `class` (extends `VideoSource`)

Loads video frames from a local file using OpenCV.

#### Constructor

```python
LocalVideoSource(filepath: str)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `filepath` | `str` | Path to the local video file |

**Raises:** `ValueError` if the video file cannot be opened.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `filepath` | `str` | Path to the local video file |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_metadata()` | None | `VideoMetadata` | Get metadata about the video file |
| `iter_frames()` | None | `Iterator[Tuple[np.ndarray, FrameContext]]` | Iterate over frames in the video |
| `process_gopro(processed_path, overwrite=False)` | `Path`, `bool` | `None` | Strip audio stream from GoPro video using ffmpeg |
| `close()` | None | `None` | Release the video capture resource |

#### Example

```python
with LocalVideoSource("footage/clip_001.ts") as source:
    metadata = source.get_metadata()
    print(f"Processing {metadata.duration:.1f}s video")
    
    for frame, context in source.iter_frames():
        # process frame
        pass
```

---

### S3VideoSource

```python
from engine.source import S3VideoSource
```

**Module:** `engine.source.s3`

**Type:** `class` (extends `VideoSource`)

Loads video frames from an AWS S3 bucket using pre-signed URLs and OpenCV HTTP streaming.

#### Constructor

```python
S3VideoSource(
    uri: str,
    presigned_url_expiry: int = 14400,
    region_name: Optional[str] = None,
    profile_name: Optional[str] = None
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `uri` | `str` | required | S3 URI (e.g., `"s3://bucket/path/video.ts"`) |
| `presigned_url_expiry` | `int` | `14400` | Pre-signed URL expiry time in seconds (default: 4 hours) |
| `region_name` | `Optional[str]` | `None` | AWS region name |
| `profile_name` | `Optional[str]` | `None` | AWS SSO profile name for authentication |

**Raises:**
- `ImportError` if boto3 is not installed
- `ValueError` if the URI is invalid

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `uri` | `str` | S3 URI to the video file |
| `bucket` | `str` | S3 bucket name (parsed from URI) |
| `key` | `str` | S3 object key (parsed from URI) |
| `presigned_url_expiry` | `int` | Pre-signed URL expiry time |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_metadata()` | None | `VideoMetadata` | Get metadata about the video file |
| `iter_frames()` | None | `Iterator[Tuple[np.ndarray, FrameContext]]` | Iterate over frames in the video |
| `close()` | None | `None` | Release the video capture resource |

#### Example

```python
with S3VideoSource("s3://my-bucket/footage/clip_001.ts", profile_name="my-profile") as source:
    metadata = source.get_metadata()
    for frame, context in source.iter_frames():
        # process frame
        pass
```

---

## Discovery Functions

### discover_local_videos

```python
from engine.source import discover_local_videos
```

**Module:** `engine.source.discovery`

Discover video files on the local file system.

#### Signature

```python
def discover_local_videos(
    path: str,
    pattern: str = "*.ts"
) -> List[VideoSource]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | required | Path to a video file or directory containing videos |
| `pattern` | `str` | `"*.ts"` | Glob pattern to match video files in directories |

**Returns:** `List[LocalVideoSource]` - List of unopened video source instances.

**Raises:**
- `FileNotFoundError` if the path does not exist
- `ValueError` if no video files are found in the directory

---

### discover_s3_videos

```python
from engine.source import discover_s3_videos
```

**Module:** `engine.source.discovery`

Discover video files in an S3 bucket.

#### Signature

```python
def discover_s3_videos(
    bucket: str,
    prefix: str = "",
    pattern: str = "*.ts",
    region_name: Optional[str] = None,
    profile_name: Optional[str] = None
) -> List[VideoSource]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bucket` | `str` | required | S3 bucket name |
| `prefix` | `str` | `""` | Key prefix to filter objects |
| `pattern` | `str` | `"*.ts"` | Glob pattern for matching video filenames |
| `region_name` | `Optional[str]` | `None` | AWS region name |
| `profile_name` | `Optional[str]` | `None` | AWS SSO profile name |

**Returns:** `List[S3VideoSource]` - List of S3VideoSource instances (not yet connected).

**Raises:**
- `ImportError` if boto3 is not installed
- `ValueError` if no matching video files are found

---

## Detectors

### Detection

```python
from engine.detectors import Detection
```

**Module:** `engine.detectors.base`

**Type:** `dataclass`

Represents a single detection in a video frame.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_file` | `str` | Path of the original source file |
| `timestamp` | `float` | Timestamp within the video (seconds from start) |
| `frame_number` | `int` | Frame index within the video |
| `xc` | `float` | X coordinate of the detection center (pixels) |
| `yc` | `float` | Y coordinate of the detection center (pixels) |
| `width` | `float` | Width of the detection bounding box (pixels) |
| `height` | `float` | Height of the detection bounding box (pixels) |
| `confidence` | `Optional[float]` | Confidence score (0.0 to 1.0), or None if not applicable |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `to_csv_row()` | None | `dict` | Convert the detection to a CSV row dictionary |

---

### DetectorBase

```python
from engine.detectors import DetectorBase
```

**Module:** `engine.detectors.base`

**Type:** `ABC` (Abstract Base Class)

Abstract base class for all detectors.

#### Abstract Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `process_frame(frame, context)` | `np.ndarray`, `FrameContext` | `Iterator[Detection]` | Process a frame and yield detections |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `reset()` | None | `None` | Reset detector state for a new video file |
| `__enter__()` | None | `DetectorBase` | Context manager entry |
| `__exit__()` | exc_type, exc_val, exc_tb | `bool` | Context manager exit with cleanup |

---

### MotionDetector

```python
from engine.detectors.motion import MotionDetector
```

**Module:** `engine.detectors.motion.detector`

**Type:** `class` (extends `DetectorBase`)

Detects motion in video frames using background subtraction with optional stabilisation.

#### Constructor

```python
MotionDetector(config: Optional[MotionDetectorConfig] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[MotionDetectorConfig]` | `None` | Configuration for the motion detector |

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `MotionDetectorConfig` | Current configuration |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `process_frame(frame, context)` | `np.ndarray`, `FrameContext` | `Iterator[Detection]` | Process a frame and yield motion detections |
| `reset()` | None | `None` | Reset internal state between videos |

#### Pipeline Stages

1. **Stabilisation** (optional) - Compensate for camera motion
2. **Background subtraction** - MOG2 adaptive model
3. **Morphological cleaning** - Remove noise, fill gaps
4. **Contour extraction** - Find candidate blobs
5. **Size filtering** - Reject too small/large
6. **Persistence filtering** - Require consistent tracks

---

### MotionDetectorConfig

```python
from engine.detectors.motion import MotionDetectorConfig
```

**Module:** `engine.detectors.motion.detector`

**Type:** `dataclass`

Configuration for the motion detector.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `stabiliser` | `StabiliserConfig` | `StabiliserConfig()` | Frame stabiliser configuration |
| `background` | `BackgroundConfig` | `BackgroundConfig()` | Background subtraction configuration |
| `stabilisation_enabled` | `bool` | `True` | Enable frame stabilisation |
| `min_area` | `int` | `100` | Minimum contour area in pixels |
| `max_area` | `int` | `50000` | Maximum contour area in pixels |
| `morph_kernel_size` | `int` | `5` | Kernel size for morphological operations |
| `morph_iterations` | `int` | `2` | Number of morphological iterations |
| `persistence_enabled` | `bool` | `True` | Enable persistence filtering |
| `min_persistence` | `int` | `3` | Frames before emitting detection |
| `max_frames_missing` | `int` | `5` | Frames before dropping track |
| `iou_threshold` | `float` | `0.3` | Minimum IoU to match detections |

---

## Motion Detection Components

### FrameStabiliser

```python
from engine.detectors.motion import FrameStabiliser
```

**Module:** `engine.detectors.motion.stabiliser`

**Type:** `class`

Stabilises frames by aligning to the previous frame using feature-based homography.

#### Constructor

```python
FrameStabiliser(config: Optional[StabiliserConfig] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[StabiliserConfig]` | `None` | Stabiliser configuration |

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `StabiliserConfig` | Current configuration |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `stabilise(frame)` | `np.ndarray` | `Tuple[np.ndarray, bool]` | Stabilise a frame, returns (frame, was_stabilised) |
| `reset()` | None | `None` | Reset the stabiliser state |

---

### StabiliserConfig

```python
from engine.detectors.motion import StabiliserConfig
```

**Module:** `engine.detectors.motion.stabiliser`

**Type:** `dataclass`

Configuration for frame stabilisation.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `feature_detector` | `str` | `"ORB"` | Feature detector type (`"ORB"` or `"AKAZE"`) |
| `max_features` | `int` | `500` | Maximum number of features to detect |
| `match_ratio` | `float` | `0.75` | Lowe's ratio test threshold for feature matching |
| `min_matches` | `int` | `10` | Minimum matches to compute homography |
| `ransac_threshold` | `float` | `5.0` | RANSAC reprojection threshold |

---

### BackgroundModel

```python
from engine.detectors.motion import BackgroundModel
```

**Module:** `engine.detectors.motion.background`

**Type:** `class`

Adaptive background subtraction using MOG2 algorithm.

#### Constructor

```python
BackgroundModel(config: Optional[BackgroundConfig] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[BackgroundConfig]` | `None` | Background model configuration |

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `BackgroundConfig` | Current configuration |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `apply(frame)` | `np.ndarray` | `np.ndarray` | Apply background subtraction, returns binary mask |
| `reset()` | None | `None` | Reset the background model |

---

### BackgroundConfig

```python
from engine.detectors.motion import BackgroundConfig
```

**Module:** `engine.detectors.motion.background`

**Type:** `dataclass`

Configuration for background subtraction.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `history` | `int` | `600` | Frames used to build background model |
| `var_threshold` | `float` | `16.0` | Variance threshold for foreground classification |
| `detect_shadows` | `bool` | `True` | Whether to detect shadows |
| `learning_rate` | `float` | `-1.0` | Learning rate (-1 for auto, or 0.0-1.0) |

---

### PersistenceTracker

```python
from engine.detectors.motion.tracker import PersistenceTracker
```

**Module:** `engine.detectors.motion.tracker`

**Type:** `class`

Tracks detections across frames and filters out transient noise.

#### Constructor

```python
PersistenceTracker(config: Optional[TrackerConfig] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[TrackerConfig]` | `None` | Tracker configuration |

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `TrackerConfig` | Current configuration |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `update(detections)` | `List[dict]` | `List[TrackedObject]` | Update tracker with new detections, returns confirmed tracks |
| `reset()` | None | `None` | Reset tracker state for a new video |

---

### TrackerConfig

```python
from engine.detectors.motion.tracker import TrackerConfig
```

**Module:** `engine.detectors.motion.tracker`

**Type:** `dataclass`

Configuration for the persistence tracker.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_persistence` | `int` | `3` | Frames before emitting detection |
| `max_frames_missing` | `int` | `5` | Frames before dropping track |
| `iou_threshold` | `float` | `0.3` | Minimum IoU to match detections |

---

### TrackedObject

```python
from engine.detectors.motion.tracker import TrackedObject
```

**Module:** `engine.detectors.motion.tracker`

**Type:** `dataclass`

A tracked detection across multiple frames.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `track_id` | `int` | required | Unique track identifier |
| `xc` | `float` | required | X coordinate of center |
| `yc` | `float` | required | Y coordinate of center |
| `width` | `float` | required | Bounding box width |
| `height` | `float` | required | Bounding box height |
| `age` | `int` | `1` | Frames since first seen |
| `frames_since_update` | `int` | `0` | Frames since last matched |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `bbox` | `Tuple[float, float, float, float]` | Bounding box as (x1, y1, x2, y2) |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `update(xc, yc, width, height)` | `float` × 4 | `None` | Update with new detection data |
| `mark_missed()` | None | `None` | Mark that no detection matched this frame |

---

## Postprocessor

### DetectionWriter

```python
from engine import DetectionWriter
```

**Module:** `engine.postprocessor`

**Type:** `class`

Writes detection results to CSV files.

#### Constructor

```python
DetectionWriter(config: Optional[PostprocessorConfig] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[PostprocessorConfig]` | `None` | Output configuration |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `detection_count` | `int` | Total number of detections written |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `write(detection)` | `Detection` | `None` | Write a single detection to CSV |
| `write_batch(detections)` | `List[Detection]` | `None` | Write a batch of detections |
| `finalise_video(source_file)` | `str` | `None` | Ensure CSV created even if no detections |
| `close()` | None | `None` | Close any open files |
| `__enter__()` | None | `DetectionWriter` | Context manager entry |
| `__exit__()` | exc_type, exc_val, exc_tb | `bool` | Context manager exit |

#### Example

```python
config = PostprocessorConfig(
    output_dir="./results",
    output_mode=OutputMode.PER_VIDEO,
    overwrite=True
)

with DetectionWriter(config) as writer:
    for detection in detections:
        writer.write(detection)
```

---

### PostprocessorConfig

```python
from engine import PostprocessorConfig
```

**Module:** `engine.postprocessor`

**Type:** `dataclass`

Configuration for the detection postprocessor.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_dir` | `str` | `"./output"` | Directory for CSV output |
| `output_mode` | `OutputMode` | `OutputMode.PER_VIDEO` | Single file or per-video output |
| `single_file_name` | `str` | `"detections.csv"` | Filename for single file mode |
| `overwrite` | `bool` | `False` | Whether to overwrite existing files |

---

### OutputMode (Postprocessor)

```python
from engine import OutputMode
```

**Module:** `engine.postprocessor`

**Type:** `Enum`

Output mode for detection results.

#### Values

| Value | Description |
|-------|-------------|
| `SINGLE_FILE` | All detections in one CSV file |
| `PER_VIDEO` | Separate CSV file for each video |

---

## Visualiser

### LiveVisualiser

```python
from engine.visualiser import LiveVisualiser
```

**Module:** `engine.visualiser.visualiser`

**Type:** `class`

Visualiser for integration with the detection pipeline. Called frame-by-frame as detections are generated.

#### Constructor

```python
LiveVisualiser(
    config: Optional[VisualiserConfig] = None,
    name_function: Optional[OutputNameFunction] = None
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[VisualiserConfig]` | `None` | Visualisation configuration |
| `name_function` | `Optional[OutputNameFunction]` | `None` | Custom output filename function |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `start_video(metadata)` | `VideoMetadata` | `None` | Begin visualisation for a new video |
| `process_frame(frame, detections, context)` | `np.ndarray`, `List[Detection]`, `FrameContext` | `Optional[AnnotatedFrame]` | Process a frame with detections |
| `end_video()` | None | `VisualisationResult` | Finish visualisation for current video |
| `__enter__()` | None | `LiveVisualiser` | Context manager entry |
| `__exit__()` | exc_type, exc_val, exc_tb | `bool` | Context manager exit |

#### Example

```python
visualiser = LiveVisualiser(config)

for source in sources:
    visualiser.start_video(source.get_metadata())
    
    for frame, context in source.iter_frames():
        detections = list(detector.process_frame(frame, context))
        annotated = visualiser.process_frame(frame, detections, context)
    
    result = visualiser.end_video()
    print(result.summary())
```

---

### PostHocVisualiser

```python
from engine.visualiser import PostHocVisualiser
```

**Module:** `engine.visualiser.visualiser`

**Type:** `class`

Visualiser for post-hoc processing from CSV detection files.

#### Constructor

```python
PostHocVisualiser(
    config: Optional[VisualiserConfig] = None,
    name_function: Optional[OutputNameFunction] = None
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[VisualiserConfig]` | `None` | Visualisation configuration |
| `name_function` | `Optional[OutputNameFunction]` | `None` | Custom output filename function |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `visualise(video_source, csv_path)` | `VideoSource`, `str` | `Iterator[AnnotatedFrame]` | Visualise video with detections from CSV |
| `visualise_from_source(video_source, detection_source)` | `VideoSource`, `DetectionSource` | `Iterator[AnnotatedFrame]` | Visualise with custom detection source |

---

### FrameAnnotator

```python
from engine.visualiser import FrameAnnotator
```

**Module:** `engine.visualiser.annotator`

**Type:** `class`

Draws detection annotations on video frames. Stateless and reusable across frames and videos.

#### Constructor

```python
FrameAnnotator(
    bbox_style: Optional[BoundingBoxStyle] = None,
    label_style: Optional[LabelStyle] = None,
    overlay_style: Optional[OverlayStyle] = None
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bbox_style` | `Optional[BoundingBoxStyle]` | `None` | Bounding box rendering style |
| `label_style` | `Optional[LabelStyle]` | `None` | Label rendering style |
| `overlay_style` | `Optional[OverlayStyle]` | `None` | Frame overlay style |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `annotate_frame(frame, detections, context, copy)` | `np.ndarray`, `List[Detection]`, `Optional[FrameContext]`, `bool` | `np.ndarray` | Draw detections and overlays on frame |

---

### VideoWriterHandle

```python
from engine.visualiser import VideoWriterHandle
```

**Module:** `engine.visualiser.writer`

**Type:** `dataclass`

Manages the lifecycle of a video file writer.

#### Constructor

```python
VideoWriterHandle(
    config: VideoOutputConfig,
    metadata: VideoMetadata,
    name_function: Optional[OutputNameFunction] = None
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `VideoOutputConfig` | required | Video output configuration |
| `metadata` | `VideoMetadata` | required | Source video metadata |
| `name_function` | `Optional[OutputNameFunction]` | `None` | Custom output filename function |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `frame_count` | `int` | Number of frames written |
| `output_path` | `Optional[Path]` | Output file path |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `write(frame)` | `np.ndarray` | `None` | Write a frame to the video file |
| `close()` | None | `None` | Release the video writer resource |
| `__enter__()` | None | `VideoWriterHandle` | Context manager entry |
| `__exit__()` | exc_type, exc_val, exc_tb | `bool` | Context manager exit |

---

### AnnotatedFrame

```python
from engine.visualiser import AnnotatedFrame
```

**Module:** `engine.visualiser.visualiser`

**Type:** `dataclass`

Container for an annotated frame (for streaming output).

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `frame` | `np.ndarray` | Annotated BGR image |
| `frame_number` | `int` | Frame index |
| `timestamp` | `float` | Timestamp in seconds |
| `detections` | `List[Detection]` | Detections in this frame |
| `source_file` | `str` | Source video path/URI |

---

### VisualisationResult

```python
from engine.visualiser import VisualisationResult
```

**Module:** `engine.visualiser.visualiser`

**Type:** `dataclass`

Result statistics from visualisation.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `source_file` | `str` | Source video path/URI |
| `output_path` | `Optional[str]` | Output video path (None if stream only) |
| `total_frames` | `int` | Total frames processed |
| `frames_with_detections` | `int` | Frames containing detections |
| `total_detections` | `int` | Total detection count |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `summary()` | None | `str` | Human-readable summary |

---

## Visualiser Configuration

### VisualiserConfig

```python
from engine.visualiser import VisualiserConfig
```

**Module:** `engine.visualiser.config`

**Type:** `dataclass`

Main configuration for the visualiser module.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_mode` | `OutputMode` | `OutputMode.FILE` | Output mode (FILE, STREAM, BOTH) |
| `video_output` | `VideoOutputConfig` | `VideoOutputConfig()` | Video file output settings |
| `bbox_style` | `BoundingBoxStyle` | `BoundingBoxStyle()` | Bounding box style |
| `label_style` | `LabelStyle` | `LabelStyle()` | Label style |
| `overlay_style` | `OverlayStyle` | `OverlayStyle()` | Frame overlay style |
| `min_confidence` | `Optional[float]` | `None` | Minimum confidence to visualise |
| `only_frames_with_detections` | `bool` | `False` | Only visualise frames with detections |
| `frame_skip` | `int` | `1` | Process every Nth frame |

---

### VideoOutputConfig

```python
from engine.visualiser import VideoOutputConfig
```

**Module:** `engine.visualiser.config`

**Type:** `dataclass`

Configuration for video file output.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_dir` | `str` | `"./visualised_output"` | Output directory |
| `filename_suffix` | `str` | `"_visualised"` | Suffix added to filename stem |
| `codec` | `str` | `"mp4v"` | FourCC codec string |
| `format` | `str` | `".mp4"` | Output file extension |
| `fps` | `Optional[float]` | `None` | Output FPS (None = match source) |
| `overwrite` | `bool` | `False` | Overwrite existing files |
| `include_parent_dirs` | `int` | `2` | Parent directory levels in output name |

---

### BoundingBoxStyle

```python
from engine.visualiser import BoundingBoxStyle
```

**Module:** `engine.visualiser.config`

**Type:** `dataclass`

Style configuration for bounding box rendering.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `draw_box` | `bool` | `True` | Whether to draw the bounding box |
| `colour` | `Tuple[int, int, int]` | `(0, 255, 0)` | BGR colour for the box |
| `thickness` | `int` | `2` | Line thickness in pixels |
| `draw_centre` | `bool` | `False` | Whether to draw centre point |
| `centre_radius` | `int` | `3` | Centre point radius |
| `centre_colour` | `Tuple[int, int, int]` | `(0, 255, 0)` | BGR colour for centre |

---

### LabelStyle

```python
from engine.visualiser import LabelStyle
```

**Module:** `engine.visualiser.config`

**Type:** `dataclass`

Style configuration for label rendering.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `True` | Whether to draw labels |
| `font_scale` | `float` | `0.5` | Font scale factor |
| `font_thickness` | `int` | `1` | Font thickness |
| `colour` | `Tuple[int, int, int]` | `(255, 255, 255)` | BGR text colour |
| `background_colour` | `Optional[Tuple[int, int, int]]` | `(0, 0, 0)` | BGR background colour |
| `position` | `LabelPosition` | `LabelPosition.TOP_LEFT` | Label position relative to box |
| `padding` | `int` | `2` | Padding around text |
| `show_confidence` | `bool` | `True` | Show confidence score |
| `show_frame_number` | `bool` | `False` | Show frame number |
| `custom_format` | `Optional[str]` | `None` | Custom format string |

---

### OverlayStyle

```python
from engine.visualiser import OverlayStyle
```

**Module:** `engine.visualiser.config`

**Type:** `dataclass`

Style configuration for frame-level overlay information.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `False` | Whether to draw overlay |
| `show_frame_number` | `bool` | `True` | Show frame number |
| `show_timestamp` | `bool` | `True` | Show timestamp |
| `show_detection_count` | `bool` | `True` | Show detection count |
| `font_scale` | `float` | `0.6` | Font scale factor |
| `font_thickness` | `int` | `1` | Font thickness |
| `colour` | `Tuple[int, int, int]` | `(255, 255, 255)` | BGR text colour |
| `background_colour` | `Optional[Tuple[int, int, int]]` | `(0, 0, 0)` | BGR background colour |
| `position` | `Tuple[int, int]` | `(10, 25)` | Top-left corner offset |

---

### OutputMode (Visualiser)

```python
from engine.visualiser import OutputMode
```

**Module:** `engine.visualiser.config`

**Type:** `Enum`

Output mode for the visualiser.

#### Values

| Value | Description |
|-------|-------------|
| `FILE` | Write frames to video file |
| `STREAM` | Yield frames for GUI integration |
| `BOTH` | Write to file and yield for GUI |

---

### LabelPosition

```python
from engine.visualiser import LabelPosition
```

**Module:** `engine.visualiser.config`

**Type:** `Enum`

Position of label relative to bounding box.

#### Values

| Value | Description |
|-------|-------------|
| `TOP_LEFT` | Top-left corner of bounding box |
| `TOP_RIGHT` | Top-right corner of bounding box |
| `BOTTOM_LEFT` | Bottom-left corner of bounding box |
| `BOTTOM_RIGHT` | Bottom-right corner of bounding box |
| `ABOVE` | Centered above the bounding box |
| `BELOW` | Centered below the bounding box |

---

## Detection Loaders

### DetectionSource

```python
from engine.visualiser import DetectionSource
```

**Module:** `engine.visualiser.loader`

**Type:** `ABC` (Abstract Base Class)

Abstract base class for loading detections.

#### Abstract Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_detections_for_frame(frame_number)` | `int` | `List[Detection]` | Get detections for a specific frame |
| `get_source_file()` | None | `str` | Get source video file path |
| `get_frame_numbers_with_detections()` | None | `List[int]` | Get sorted list of frames with detections |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_total_detection_count()` | None | `int` | Get total detection count |
| `get_frame_count_with_detections()` | None | `int` | Get number of frames with detections |

---

### CSVDetectionLoader

```python
from engine.visualiser import CSVDetectionLoader
```

**Module:** `engine.visualiser.loader`

**Type:** `class` (extends `DetectionSource`)

Load detections from a CSV file.

#### Constructor

```python
CSVDetectionLoader(
    csv_path: str,
    source_file: Optional[str] = None
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `csv_path` | `str` | required | Path to CSV file with detections |
| `source_file` | `Optional[str]` | `None` | Filter to only load detections for this source |

**Raises:**
- `FileNotFoundError` if CSV file does not exist
- `ValueError` if CSV is missing required columns

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `csv_path` | `Path` | Path to the CSV file |
| `sources_in_file` | `List[str]` | All source files found in the CSV |

#### Required CSV Columns

`source_file`, `timestamp`, `frame_number`, `xc`, `yc`, `width`, `height`

#### Optional CSV Columns

`confidence`

---

### FrameDetections

```python
from engine.visualiser import FrameDetections
```

**Module:** `engine.visualiser.loader`

**Type:** `dataclass`

Container for detections grouped by frame number.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_file` | `str` | required | Path or URI of the source file |
| `detections_by_frame` | `Dict[int, List[Detection]]` | `{}` | Detections indexed by frame number |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `get_detections_for_frame(frame_number)` | `int` | `List[Detection]` | Get detections for a frame |
| `get_frame_numbers_with_detections()` | None | `List[int]` | Get sorted list of frames with detections |
| `add_detection(detection)` | `Detection` | `None` | Add a detection to the appropriate frame |
| `get_total_detection_count()` | None | `int` | Get total number of detections |

---

### IteratorDetectionSource

```python
from engine.visualiser import IteratorDetectionSource
```

**Module:** `engine.visualiser.loader`

**Type:** `class` (extends `DetectionSource`)

Wrap an iterator of detections for use with visualiser. Buffers all detections in memory.

#### Constructor

```python
IteratorDetectionSource(
    detections: Iterator[Detection],
    source_file: str
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `detections` | `Iterator[Detection]` | Iterator yielding Detection objects |
| `source_file` | `str` | Source video file path/URI |

**Note:** The iterator is fully consumed during initialisation.

---

### ListDetectionSource

```python
from engine.visualiser import ListDetectionSource
```

**Module:** `engine.visualiser.loader`

**Type:** `class` (extends `DetectionSource`)

Create detection source from a list of detections.

#### Constructor

```python
ListDetectionSource(
    detections: List[Detection],
    source_file: str
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `detections` | `List[Detection]` | List of Detection objects |
| `source_file` | `str` | Source video file path/URI |

---

## Pipeline

### DetectionPipeline

```python
from pipeline import DetectionPipeline
```

**Module:** `pipeline`

**Type:** `class`

Main pipeline for processing videos and detecting objects.

#### Constructor

```python
DetectionPipeline(
    config: Optional[PipelineConfig] = None,
    detector_factory: Optional[Callable[[], DetectorBase]] = None
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[PipelineConfig]` | `None` | Pipeline configuration |
| `detector_factory` | `Optional[Callable[[], DetectorBase]]` | `None` | Factory function returning detector instances |

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `PipelineConfig` | Current configuration |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `process_sources(sources, dry_run)` | `List[VideoSource]`, `bool` | `PipelineResult` or `DryRunResult` | Process video sources |

#### Example

```python
from engine import discover_local_videos
from pipeline import DetectionPipeline, PipelineConfig

sources = discover_local_videos("./data/footage/", "*.ts")
config = PipelineConfig()
pipeline = DetectionPipeline(config)
result = pipeline.process_sources(sources)
print(result.summary())
```

---

### PipelineConfig

```python
from pipeline import PipelineConfig
```

**Module:** `pipeline`

**Type:** `dataclass`

Configuration for the detection pipeline.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `input` | `InputConfig` | `InputConfig()` | Input processing configuration |
| `output` | `PostprocessorConfig` | `PostprocessorConfig()` | Output configuration |
| `detector` | `DetectorConfig` | `DetectorConfig()` | Detector configuration |
| `resume` | `bool` | `True` | Skip videos with existing output files |
| `visualiser` | `Optional[VisualiserConfig]` | `None` | Visualiser configuration |

#### Class Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `from_dict(data)` | `dict` | `PipelineConfig` | Create config from dictionary (e.g., YAML) |

---

### InputConfig

```python
from pipeline import InputConfig
```

**Module:** `pipeline`

**Type:** `dataclass`

Configuration for pipeline input processing.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `frame_skip` | `int` | `1` | Process every Nth frame |

---

### DetectorConfig

```python
from pipeline import DetectorConfig
```

**Module:** `pipeline`

**Type:** `dataclass`

Configuration for detector selection and settings.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | `str` | `"motion"` | Detector type name |
| `config` | `dict` | `{}` | Detector-specific configuration |

---

### PipelineResult

```python
from pipeline import PipelineResult
```

**Module:** `pipeline`

**Type:** `dataclass`

Results from a pipeline run.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `videos_processed` | `int` | `0` | Videos successfully processed |
| `videos_skipped` | `int` | `0` | Videos skipped (resume mode) |
| `videos_failed` | `int` | `0` | Videos that failed processing |
| `total_detections` | `int` | `0` | Total detections across all videos |
| `elapsed_time` | `float` | `0.0` | Total elapsed time in seconds |
| `detections_per_video` | `Dict` | `{}` | Video path → detection count |
| `failed_videos` | `Dict` | `{}` | Video path → error message |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `summary()` | None | `str` | Human-readable summary |

---

### DryRunResult

```python
from pipeline import DryRunResult
```

**Module:** `pipeline`

**Type:** `dataclass`

Results from a dry run.

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `videos_found` | `int` | `0` | Number of video files found |
| `videos_to_process` | `int` | `0` | Videos that would be processed |
| `videos_skipped` | `int` | `0` | Videos that would be skipped |
| `total_frames` | `int` | `0` | Total frames across all videos |
| `total_duration` | `float` | `0.0` | Total duration in seconds |
| `output_mode` | `str` | `""` | Output mode that would be used |
| `output_dir` | `str` | `""` | Output directory |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `summary()` | None | `str` | Human-readable summary |

---

## Utility Functions

### extract_output_stem

```python
from engine.visualiser import extract_output_stem
```

**Module:** `engine.visualiser.writer`

Extract a suitable output filename stem from a source file path or URI.

```python
def extract_output_stem(
    source_file: str,
    include_parents: int = 2
) -> str
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_file` | `str` | required | Source file path or S3 URI |
| `include_parents` | `int` | `2` | Parent directories to include |

**Returns:** Sanitised string suitable for use as a filename stem.

---

### sanitise_filename

```python
from engine.visualiser import sanitise_filename
```

**Module:** `engine.visualiser.writer`

Sanitise a string to be safe for use as a filename.

```python
def sanitise_filename(name: str) -> str
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Input string to sanitise |

**Returns:** Sanitised filename string.

---

### load_detections_from_csv

```python
from engine.visualiser import load_detections_from_csv
```

**Module:** `engine.visualiser.loader`

Convenience function to load detections from CSV into a FrameDetections object.

```python
def load_detections_from_csv(
    csv_path: str,
    source_file: Optional[str] = None
) -> FrameDetections
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `csv_path` | `str` | required | Path to CSV file |
| `source_file` | `Optional[str]` | `None` | Optional source file filter |

**Returns:** `FrameDetections` container with loaded detections.

---

### compute_iou

```python
from engine.detectors.motion.tracker import compute_iou
```

**Module:** `engine.detectors.motion.tracker`

Compute Intersection over Union between two bounding boxes.

```python
def compute_iou(
    box1: Tuple[float, float, float, float],
    box2: Tuple[float, float, float, float]
) -> float
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `box1` | `Tuple[float, float, float, float]` | First box as (x1, y1, x2, y2) |
| `box2` | `Tuple[float, float, float, float]` | Second box as (x1, y1, x2, y2) |

**Returns:** IoU value between 0.0 and 1.0.

---

### parse_s3_uri

```python
from engine.source.s3 import parse_s3_uri
```

**Module:** `engine.source.s3`

Parse an S3 URI into bucket and key components.

```python
def parse_s3_uri(uri: str) -> Tuple[str, str]
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `uri` | `str` | S3 URI (e.g., `"s3://bucket-name/path/to/file.ts"`) |

**Returns:** Tuple of `(bucket_name, key)`.

**Raises:** `ValueError` if the URI is not valid.

---

### setup_logging

```python
from pipeline import setup_logging
```

**Module:** `pipeline`

Set up basic logging configuration.

```python
def setup_logging(level: int = logging.INFO) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `level` | `int` | `logging.INFO` | Logging level |

---

### register_detector

```python
from pipeline import register_detector
```

**Module:** `pipeline`

Register a detector type for use with YAML configuration.

```python
def register_detector(
    name: str,
    detector_class: Type[DetectorBase],
    config_parser: Callable[[dict], object]
) -> None
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Name used in config files |
| `detector_class` | `Type[DetectorBase]` | The detector class |
| `config_parser` | `Callable[[dict], object]` | Function to parse config dict |

---

## Type Aliases

### OutputNameFunction

```python
from engine.visualiser import OutputNameFunction
```

**Module:** `engine.visualiser.writer`

Type alias for custom output naming functions.

```python
OutputNameFunction = Callable[[VideoMetadata], str]
```

A function that takes `VideoMetadata` and returns a filename stem (without suffix or extension).