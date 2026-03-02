# SeaVision Class & API Reference

Updated for the current SeaVision package layout.

---

## Table of Contents

- [Package Exports](#package-exports)
- [Video Sources (`engine.source`)](#video-sources-enginesource)
- [Core Detection API (`engine.detectors.base`)](#core-detection-api-enginedetectorsbase)
- [Motion Detector (`engine.detectors.motion`)](#motion-detector-enginedetectorsmotion)
- [YOLO Detector (`engine.detectors.yolo`)](#yolo-detector-enginedetectorsyolo)
- [SAM3 Detectors (`engine.detectors.sam3`)](#sam3-detectors-enginedetectorssam3)
- [Postprocessing & CSV Output (`engine.postprocessor`)](#postprocessing--csv-output-enginepostprocessor)
- [Visualiser (`engine.visualiser`)](#visualiser-enginevisualiser)
- [Pipeline (`pipeline.py`)](#pipeline-pipelinepy)
- [Top-Level Functions](#top-level-functions)

---

## Package Exports

### `engine`

`engine.__init__` currently re-exports:

- **Sources:** `FrameContext`, `VideoMetadata`, `VideoSource`, `LocalVideoSource`, `S3VideoSource`, `discover_local_videos`, `discover_s3_videos`
- **Detection base:** `Detection`, `DetectorBase`
- **Postprocessing:** `OutputMode`, `CSVWriterConfig`, `DetectionWriter`, `FramePostprocessor`, `VideoPostprocessor`, `LabelFilterConfig`, `LabelFilter`, `PerFrameNmsConfig`, `PerFrameNmsPostprocessor`, `MotionTrackVideoConfig`, `MotionTrackVideoPostprocessor`, `PostprocessStage`, `build_postprocess_stages`

### `engine.detectors`

`engine.detectors.__init__` always exports:

- `Detection`, `DetectorBase`

Conditionally exported (when dependencies are available):

- **SAM3 stack:** `SAM3Detector`, `SAM3DetectorConfig`, `PromptType`, `HybridStrategy`, `PrompterConfig`, `PromptConfig`
- **YOLO stack:** `YOLODetector`, `YOLODetectorConfig`

### `engine.visualiser`

`engine.visualiser.__init__` exports config, writer helpers, loaders, and both visualiser orchestrators.

---

## Video Sources (`engine.source`)

### `VideoMetadata` (dataclass)
**Module:** `engine.source.base`

Attributes:
- `source_file: str`
- `fps: float`
- `frame_count: int`
- `width: int`
- `height: int`
- `duration: float`

### `FrameContext` (dataclass)
**Module:** `engine.source.base`

Attributes:
- `source_file: str`
- `frame_number: int`
- `timestamp: float`
- `fps: float`

### `VideoSource` (ABC)
**Module:** `engine.source.base`

Abstract methods:
- `iter_frames() -> Iterator[Tuple[np.ndarray, FrameContext]]`
- `get_metadata() -> VideoMetadata`

Concrete methods:
- `close() -> None`
- context manager support (`__enter__`, `__exit__`)

### `LocalVideoSource` (`VideoSource`)
**Module:** `engine.source.local`

Constructor:
- `LocalVideoSource(filepath: str)`

Key methods:
- `get_metadata() -> VideoMetadata`
- `iter_frames() -> Iterator[Tuple[np.ndarray, FrameContext]]`
- `process_gopro(processed_path: Path, overwrite: bool = False) -> None`
- `close() -> None`

### `S3VideoSource` (`VideoSource`)
**Module:** `engine.source.s3`

Constructor:
- `S3VideoSource(uri, presigned_url_expiry=14400, region_name=None, profile_name=None, endpoint_url=None)`

Key methods:
- `get_metadata() -> VideoMetadata`
- `iter_frames() -> Iterator[Tuple[np.ndarray, FrameContext]]`
- `close() -> None`

### `parse_s3_uri` (function)
**Module:** `engine.source.s3`

- `parse_s3_uri(uri: str) -> Tuple[str, str]`

---

## Core Detection API (`engine.detectors.base`)

### `Detection` (dataclass)
**Module:** `engine.detectors.base`

Attributes:
- Required geometry/context: `source_file`, `timestamp`, `frame_number`, `xc`, `yc`, `width`, `height`
- Optional metadata: `confidence`, `label`, `track_id`, `mask`, `metadata`

Key methods/properties:
- `to_csv_row() -> dict`
- `bbox -> tuple` (x1, y1, x2, y2)
- `area -> float`
- `from_bbox(...) -> Detection` (classmethod)

### `DetectorBase` (ABC)
**Module:** `engine.detectors.base`

Abstract method:
- `process_frame(frame, context) -> Iterator[Detection]`

Base methods:
- `reset() -> None`
- context manager support (`__enter__`, `__exit__`)

---

## Motion Detector (`engine.detectors.motion`)

### `StabiliserConfig` (dataclass)
**Module:** `engine.detectors.motion.stabiliser`

- `feature_detector`, `max_features`, `match_ratio`, `min_matches`, `ransac_threshold`

### `FrameStabiliser`
**Module:** `engine.detectors.motion.stabiliser`

- `stabilise(frame) -> Tuple[np.ndarray, bool]`
- `reset() -> None`

### `BackgroundConfig` (dataclass)
**Module:** `engine.detectors.motion.background`

- `history`, `var_threshold`, `detect_shadows`, `learning_rate`

### `BackgroundModel`
**Module:** `engine.detectors.motion.background`

- `apply(frame) -> np.ndarray`
- `reset() -> None`

### `TrackerConfig` (dataclass)
**Module:** `engine.detectors.motion.tracker`

- `min_persistence`, `max_frames_missing`, `iou_threshold`

### `TrackedObject` (dataclass)
**Module:** `engine.detectors.motion.tracker`

- `update(xc, yc, width, height) -> None`
- `mark_missed() -> None`
- `bbox -> Tuple[float, float, float, float]`

### `PersistenceTracker`
**Module:** `engine.detectors.motion.tracker`

- `update(detections: List[dict]) -> List[TrackedObject]`
- `reset() -> None`

### `MotionDetectorConfig` (dataclass)
**Module:** `engine.detectors.motion.detector`

Includes:
- Sub-configs: `stabiliser`, `background`
- Motion extraction: `stabilisation_enabled`, `min_area`, `max_area`, `morph_kernel_size`, `morph_iterations`
- Persistence filtering: `persistence_enabled`, `min_persistence`, `max_frames_missing`, `iou_threshold`

### `MotionDetector` (`DetectorBase`)
**Module:** `engine.detectors.motion.detector`

- `process_frame(frame, context) -> Iterator[Detection]`
- `reset() -> None`

### `compute_iou` (function)
**Module:** `engine.detectors.motion.tracker`

- `compute_iou(box1, box2) -> float`

---

## YOLO Detector (`engine.detectors.yolo`)

### `YOLODetectorConfig` (dataclass)
**Module:** `engine.detectors.yolo.config`

- `model_path`, `device`, `imgsz`
- `conf_threshold`, `iou_threshold`, `max_detections`
- `classes`, `output_labels`
- `half`, `verbose`

### `YOLODetector` (`DetectorBase`)
**Module:** `engine.detectors.yolo.detector`

- Lazy-loads local Ultralytics weights
- `process_frame(frame, context) -> Iterator[Detection]`
- `reset() -> None`

---

## SAM3 Detectors (`engine.detectors.sam3`)

### Enums

#### `PromptType`
**Module:** `engine.detectors.sam3.config`

Values:
- `TEXT`
- `BOX`
- `POINT`
- `DETECTOR`

#### `HybridStrategy`
**Module:** `engine.detectors.sam3.config`

Values:
- `BOX_REFINEMENT`
- `CLASSIFY_REGIONS`

### Config Dataclasses

#### `PrompterConfig`
**Module:** `engine.detectors.sam3.config`

- `detector_type`, `detector_config`
- `strategy`
- `text_prompts`
- `min_iou_with_prompt`

#### `PromptConfig`
**Module:** `engine.detectors.sam3.config`

- Prompt type + mode-specific prompt fields:
  - `text_prompts`
  - `box_prompts`, `box_labels`
  - `point_prompts`, `point_labels`
  - `prompter` (for detector/hybrid mode)
- Video prompt policy:
  - `reprompt_interval`
  - `reprompt_on_lost`

#### `SAM3DetectorConfig`
**Module:** `engine.detectors.sam3.config`

- Model/runtime: `checkpoint`, `device`, `half`, `imgsz`
- Prompting: `prompts`, `prompt_config`
- Filtering: `confidence_threshold`, `min_mask_area`, `max_mask_area`
- Behaviour/output: `video_mode`, `output_masks`, `output_labels`
- Helper: `get_ultralytics_overrides() -> Dict`

### `SAM3Detector` (`DetectorBase`)
**Module:** `engine.detectors.sam3.detector`

Supports TEXT / BOX / POINT / DETECTOR (hybrid) prompt workflows.

Public methods:
- `process_frame(frame, context) -> Iterator[Detection]`
- `add_exemplar(box=None, point=None, positive=True) -> None`
- `clear_exemplars() -> None`
- `reset() -> None`
- context manager support (`__enter__`, `__exit__`)

### `SAM3NativeDetector` (`DetectorBase`)
**Module:** `engine.detectors.sam3.native`

Native Transformers-based backend for SAM3 (currently TEXT prompt mode).

Public methods:
- `process_frame(frame, context) -> Iterator[Detection]`
- `reset() -> None`

---

## Postprocessing & CSV Output (`engine.postprocessor`)

### `OutputMode` (Enum)
Values:
- `SINGLE_FILE`
- `PER_VIDEO`

### `CSVWriterConfig` (dataclass)
- `output_dir`, `output_mode`, `single_file_name`, `overwrite`

### Postprocessor Protocols

#### `FramePostprocessor` (Protocol)
- `reset_for_video(metadata) -> None`
- `process_frame(detections, context) -> List[Detection]`
- `finalize_video() -> None`

#### `VideoPostprocessor` (Protocol)
- `process_video(detections_per_frame, metadata, frames=None, contexts=None) -> List[List[Detection]]`

### Built-in Frame Postprocessors

#### `LabelFilterConfig` (dataclass)
- `keep_labels`, `drop_labels`

#### `LabelFilter` (`FramePostprocessor`)
- `process_frame(...) -> List[Detection]`

#### `PerFrameNmsConfig` (dataclass)
- `iou_threshold`, `class_agnostic`

#### `PerFrameNmsPostprocessor` (`FramePostprocessor`)
- `process_frame(...) -> List[Detection]`

### Built-in Video Postprocessor

#### `MotionTrackVideoConfig` (dataclass)
- `window_seconds`, `threshold_fraction`

#### `MotionTrackVideoPostprocessor` (`VideoPostprocessor`)
- Drops track IDs with insufficient displacement over time.

### Stage Wiring

#### `PostprocessStage` (dataclass)
- `kind: Literal["frame", "video"]`
- `impl: object`

#### `PostprocessorFactory` (TypedDict)
- `kind`
- `build`

#### `build_postprocess_stages(config_dict) -> List[PostprocessStage]`
- Builds ordered stages from YAML-style config.

### `DetectionWriter`

Writes detections in CSV format.

Methods:
- `write(detection) -> None`
- `write_batch(detections) -> None`
- `finalise_video(source_file) -> None`
- `close() -> None`
- `detection_count` (property)
- context manager support (`__enter__`, `__exit__`)

---

## Visualiser (`engine.visualiser`)

### Config Enums

#### `OutputMode` (`engine.visualiser.config`)
- `FILE`
- `STREAM`
- `BOTH`

#### `LabelPosition` (`engine.visualiser.config`)
- `TOP_LEFT`, `TOP_RIGHT`, `BOTTOM_LEFT`, `BOTTOM_RIGHT`, `ABOVE`, `BELOW`

### Visual Style Dataclasses

#### `BoundingBoxStyle`
- `draw_box`, `colour`, `thickness`, `draw_centre`, `centre_radius`, `centre_colour`, `class_colours`

#### `LabelStyle`
- `enabled`, `font_scale`, `font_thickness`, `colour`, `background_colour`, `position`, `padding`
- `show_label`, `show_confidence`, `show_frame_number`, `custom_format`

#### `OverlayStyle`
- `enabled`, `show_frame_number`, `show_timestamp`, `show_detection_count`
- font and placement fields

#### `VideoOutputConfig`
- `output_dir`, `filename_suffix`, `codec`, `format`, `fps`, `overwrite`, `include_parent_dirs`

#### `VisualiserConfig`
- `output_mode`, style configs, `min_confidence`, `only_frames_with_detections`, `frame_skip`

### Rendering / IO Components

#### `FrameAnnotator`
**Module:** `engine.visualiser.annotator`

- `annotate_frame(frame, detections, context=None, copy=True) -> np.ndarray`

#### `VideoWriterHandle` (dataclass)
**Module:** `engine.visualiser.writer`

- Handles output filename derivation + `cv2.VideoWriter` lifecycle
- `write(frame) -> None`
- `close() -> None`
- properties: `frame_count`, `output_path`

Writer helpers:
- `extract_output_stem(source_file, include_parents=2) -> str`
- `sanitise_filename(name) -> str`
- `OutputNameFunction` type alias

### Detection Loader Abstractions

#### `DetectionSource` (ABC)
**Module:** `engine.visualiser.loader`

- `get_detections_for_frame(frame_number)`
- `get_source_file()`
- `get_frame_numbers_with_detections()`
- convenience methods: total count / frame count

#### `FrameDetections` (dataclass)
- in-memory frame-indexed detection container

#### `CSVDetectionLoader` (`DetectionSource`)
- CSV-backed detection source with source-file filtering

#### `IteratorDetectionSource` / `ListDetectionSource` (`DetectionSource`)
- wrappers for iterator/list-backed detections

#### `load_detections_from_csv(csv_path, source_file=None) -> FrameDetections`

### Orchestrators

#### `AnnotatedFrame` (dataclass)
**Module:** `engine.visualiser.visualiser`

- `frame`, `frame_number`, `timestamp`, `detections`, `source_file`

#### `VisualisationResult` (dataclass)
- summary stats + `summary() -> str`

#### `LiveVisualiser`
- `start_video(metadata) -> None`
- `process_frame(frame, detections, context) -> Optional[AnnotatedFrame]`
- `end_video() -> VisualisationResult`

#### `PostHocVisualiser`
- `visualise(video_source, csv_path) -> Iterator[AnnotatedFrame]`
- `visualise_from_source(video_source, detection_source) -> Iterator[AnnotatedFrame]`

---

## Pipeline (`pipeline.py`)

### Config and Result Dataclasses

#### `InputConfig`
- `frame_skip`

#### `DetectorConfig`
- `type`
- `config` (detector-specific dictionary)

#### `PipelineConfig`
- `input`, `output`, `detector`, `resume`, `visualiser`, `postprocess`
- `from_dict(data) -> PipelineConfig`

#### `DryRunResult`
- scan statistics
- `summary() -> str`

#### `PipelineResult`
- processing statistics + failures
- `summary() -> str`

### `DetectionPipeline`

Core orchestration class for source processing.

Public methods:
- `process_sources(sources, dry_run=False) -> Union[PipelineResult, DryRunResult]`

Internal key methods (important for extension):
- detector creation from registry (`_create_detector_from_config`)
- dry-run/source skip logic (`_dry_run`, `_should_skip_source`)
- execution path (`_process_sources`, `_process_single_source`)

### Detector Registry Utilities

- `register_detector(name, detector_class, config_parser)`
- built-in registrations include `motion` and conditional `sam3`

### Logging Utility

- `setup_logging(level=logging.INFO) -> None`

---

## Top-Level Functions

### Source discovery
- `discover_local_videos(path, pattern="*.ts") -> List[VideoSource]`
- `discover_s3_videos(bucket, prefix="", pattern="*.ts", region_name=None, profile_name=None, endpoint_url=None) -> List[VideoSource]`

### Postprocessing stage builder
- `build_postprocess_stages(config_dict) -> List[PostprocessStage]`

### Visualiser loader utility
- `load_detections_from_csv(csv_path, source_file=None) -> FrameDetections`

### CLI (`run_pipeline.py`)
- `parse_args()`
- `load_config_file(config_path)`
- `build_config(args) -> PipelineConfig`
- `discover_sources(args, config_data=None)`
- `main() -> int`
