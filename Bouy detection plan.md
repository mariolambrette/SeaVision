# BUOY DETECTION PIPELINE - DEVELOPMENT PLAN

## Project Overview

Motion detection pipeline for marine monitoring buoy footage.
Designed to scan large volumes of footage and identify candidate detections
for later review.

## Data Specifications

- Format: .ts (transport stream)
- Resolution: 640x480 pixels
- Frame rate: 10 FPS
- Duration: ~20 seconds per video (200 frames)
- Storage: AWS S3, organized by day subfolders, timestamps in filenames
  Bucket: alga-field-processed-uploads
  Prefix: processed/{device-id}/video/{camera}/
- Sample footage available locally for development testing

## Output Specifications

- Format: CSV
- Location: Local directory (user-specified)
- Fields: source_file, timestamp, frame_number, xc, yc, width, height, confidence

## Project Structure

buoy_detection/
├── engine/
│   ├── __init__.py            # Package exports
│   ├── postprocessor.py       # Output formatting (DetectionWriter)
│   ├── source/
│   │   ├── __init__.py
│   │   ├── base.py            # VideoSource, VideoMetadata, FrameContext
│   │   ├── local.py           # LocalVideoSource (OpenCV)
│   │   ├── s3.py              # S3VideoSource (pre-signed URL streaming)
│   │   └── discovery.py       # discover_local_videos(), discover_s3_videos()
│   └── detectors/
│       ├── __init__.py
│       ├── base.py            # Detection, DetectorBase
│       └── motion/
│           ├── __init__.py
│           ├── detector.py    # MotionDetector, MotionDetectorConfig
│           ├── stabiliser.py  # FrameStabiliser, StabiliserConfig
│           ├── background.py  # BackgroundModel, BackgroundConfig
│           └── tracker.py     # PersistenceTracker, TrackerConfig
├── pipeline.py                # DetectionPipeline orchestration
├── run_pipeline.py            # CLI entry point
├── config/
│   └── default.yaml           # Example configuration file
├── tests/
│   ├── test_s3_access.py              # S3 connectivity and streaming test
│   ├── test_s3_pipeline.py            # Full pipeline test with S3 videos
│   ├── test_aquarium_visualisation.py # Aquarium footage test with visualisation
│   └── visualise_detections.py        # Detection overlay visualisation tool
├── test_output/               # Output directory for test runs
├── environment.yml            # Conda environment specification
└── requirements.txt           # Pip requirements (alternative)

## Development Steps

[1] DEFINE DATA STRUCTURES
    - Detection result dataclass
    - Abstract detector interface
    Status: COMPLETE

    Implemented:
    - Detection dataclass (engine/detectors/base.py)
      Fields: source_file, timestamp, frame_number, xc, yc, width, height, confidence
      Includes to_csv_row() method for output formatting
    - DetectorBase abstract class (engine/detectors/base.py)
      Methods: process_frame(), reset(), context manager support
    - FrameContext dataclass (engine/source/base.py)
      Fields: source_file, frame_number, timestamp, fps
    - VideoMetadata dataclass (engine/source/base.py)
      Fields: source_file, fps, frame_count, width, height, duration
    - VideoSource abstract class (engine/source/base.py)
      Methods: iter_frames(), get_metadata(), close(), context manager support

[2] BUILD SOURCE MODULE
    - Local file loader (for development/testing)
    - S3 loader (same interface, for production)
    - Discovery functions (find videos from different sources)
    Status: COMPLETE

    Implemented:
    - LocalVideoSource (engine/source/local.py)
      Uses OpenCV cv2.VideoCapture for reading video files
      Supports .ts format and any other OpenCV-compatible format
    - S3VideoSource (engine/source/s3.py)
      Streams video from S3 using pre-signed URLs
      Uses OpenCV HTTP streaming (no temp file download)
      Supports SSO profiles via profile_name parameter
      Pre-signed URL expiry: 4 hours (configurable)
      Lazy connection - only connects when first frame requested
    - discover_local_videos() (engine/source/discovery.py)
      Finds videos on local filesystem using glob patterns
    - discover_s3_videos() (engine/source/discovery.py)
      Lists S3 bucket objects matching pattern
      Supports SSO profiles via profile_name parameter
      Handles pagination for large buckets

[3] BUILD SKELETON DETECTOR
    - Implements detector interface
    - Receives frames, emits detections
    - Minimal placeholder logic initially
    Status: COMPLETE

    Implemented:
    - MotionDetector (engine/detectors/motion/detector.py)
      Full motion detection pipeline with configurable parameters
      Implements DetectorBase interface with process_frame() and reset()
    - FrameStabiliser (engine/detectors/motion/stabiliser.py)
      Feature-based homography using ORB/AKAZE detectors
    - BackgroundModel (engine/detectors/motion/background.py)
      MOG2 adaptive background subtraction

[4] BUILD POSTPROCESSOR
    - Writes CSV in specified format
    - Handles filename and timestamp formatting
    Status: COMPLETE

    Implemented:
    - PostprocessorConfig (engine/postprocessor.py)
      Configurable output directory, output mode, and filename
      Overwrite protection (must set overwrite=True to replace existing files)
    - OutputMode enum: SINGLE_FILE or PER_VIDEO modes
    - DetectionWriter (engine/postprocessor.py)
      Context manager for writing detections to CSV
      Supports single file for all videos or one CSV per video
      finalise_video() ensures empty videos get CSV files

[5] WIRE UP AND TEST LOCALLY
    - End-to-end flow on sample footage
    - Confirm all components connect properly
    Status: COMPLETE

    Implemented:
    - DetectionPipeline class (pipeline.py)
      Orchestrates source → detector → writer flow
      process_sources() method accepts any VideoSource list
      Supports dry_run mode for scanning without processing
      Resume mode skips videos with existing output
      Frame skipping for faster preview runs
      Nested progress bars (video-level and frame-level)
      Error handling with continue-on-failure
    - Detector registry system
      register_detector() for adding new detector types
      Supports factory function for programmatic detector creation
    - Configuration system
      PipelineConfig with from_dict() for YAML loading
      InputConfig, DetectorConfig dataclasses
    - Result classes
      PipelineResult and DryRunResult with summary() methods
    - run_pipeline.py CLI entry point
      Argparse with grouped options (input, output, processing, detector)
      YAML config file support with CLI overrides
      Verbose logging flag
    - config/default.yaml example configuration
    - environment.yml and requirements.txt for dependencies
    
    Tested:
    - Successfully processed 12 test videos (891 detections in 9 seconds)
    - Frame-skip mode working (--frame-skip 10)
    - Resume mode working (skips existing outputs)
    - Per-video CSV output working

[6] IMPLEMENT MOTION DETECTION LOGIC
    - Frame stabilization (compensate for buoy sway)
    - Adaptive background subtraction
    - Foreground filtering (size, persistence, motion coherence)
    Status: COMPLETE

    Implemented:
    - Frame stabilization via FrameStabiliser (feature-based homography)
    - Adaptive background via BackgroundModel (MOG2)
    - Size filtering in MotionDetector (min_area, max_area)
    - Morphological cleanup (opening/closing operations)
    - Persistence filtering via PersistenceTracker (multi-frame tracking)
      - IoU-based greedy matching between frames
      - Configurable min_persistence (frames before emitting)
      - Configurable max_frames_missing (frames before dropping track)
    
    Not implemented (may not be needed):
    - Motion coherence filtering (smooth trajectory validation)
      Initial testing suggests persistence filtering is sufficient

[7] ADD S3 SOURCE
    - Swap in S3 loader for real data
    - Test with actual bucket structure
    Status: COMPLETE

    Implemented:
    - S3VideoSource using pre-signed URLs + OpenCV HTTP streaming
    - discover_s3_videos() with pagination and pattern matching
    - SSO profile support (profile_name parameter) for IAM Identity Center
    - boto3 dependency added to environment.yml and requirements.txt
    
    Authentication options:
    - SSO profile: profile_name="m3b-detector" (recommended)
    - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    - IAM role: automatic on EC2/Lambda
    - Credentials file: ~/.aws/credentials
    
    Usage:
        # Login to SSO (required before first use, lasts 8-12 hours)
        aws sso login --profile m3b-detector
        
        # Discover and process S3 videos
        sources = discover_s3_videos(
            bucket="your-bucket",
            prefix="footage/2025/",
            profile_name="m3b-detector"
        )
        result = pipeline.process_sources(sources)
    
    Tested:
    - OpenCV successfully streams .ts files via pre-signed URLs
    - Full pipeline tested on 10 S3 videos
    - Test scripts: tests/test_s3_access.py, tests/test_s3_pipeline.py

[8] TUNE PARAMETERS
    - Adjust on real footage
    - Document final parameter choices
    Status: IN PROGRESS

    Testing conducted on aquarium footage (high activity density):
    - Default settings: ~4,400 detections / 10 videos
    - Sensitive settings: 33,036 detections (too noisy)
    - Tuned settings: 11,396 detections (better balance)
    - Anti-flicker settings: 6,009 detections (reduced noise)
    
    Parameter experiments (see tests/test_aquarium_visualisation.py):
    - learning_rate: 0.001 (slow adaptation helps with flicker)
    - var_threshold: 18 (higher = less sensitive to brightness changes)
    - detect_shadows: False (reduces flicker artifacts)
    - min_area: 450 (filter small noise)
    - min_persistence: 8 (strict - require consistent tracks)
    - max_frames_missing: 2 (tight tracks only)
    - history: 1000 (stable background model)
    
    Key findings:
    - Aquarium footage (high activity) ≠ sea footage (sparse activity)
    - For sparse footage, precision > recall (false positives waste review time)
    - Lighting flicker is a significant noise source
    - Persistence filtering effective for removing transient noise
    
    Remaining:
    - Test on actual sea deployment footage
    - Develop validation strategy for unlabeled data
    - Document final recommended parameters for each scenario

[9] VALIDATION STRATEGY
    - Approach for validating pipeline on unlabeled sea footage
    Status: PLANNED

    Challenge:
    - Thousands of hours of footage
    - Unknown base rate of animal activity
    - Cannot manually review everything
    
    Proposed approach:
    1. Stratified sampling:
       - Sample videos with HIGH detection counts → check precision
       - Sample videos with ZERO detections → check for false negatives
       - Random sample → baseline statistics
    
    2. Detection-guided review:
       - Only review frames with detections (visualiser already supports this)
       - Flag detections as TP/FP to estimate precision
       - Fast since only examining flagged frames
    
    3. Cluster analysis:
       - Identify videos with unusual detection counts
       - Investigate outliers (equipment issues, algae, or genuine activity)
       - Analyze patterns by time of day, location, conditions
    
    4. Iterative refinement:
       - Run pipeline with conservative settings
       - Sample and review detections
       - Tune parameters based on error patterns
       - Re-run on subset, repeat until acceptable

## Motion Detection Approach

### Challenges

- Buoy sway causing camera movement
- Variable natural lighting (no artificial light)
- Water noise (particles, bubbles, sediment)
- Lighting flicker from water surface/artificial sources

### Proposed solution

1. Frame stabilization using feature-based homography
2. Adaptive background model (MOG2)
3. Morphological cleanup of foreground mask
4. Contour detection for candidate blobs
5. Filtering by size (min_area, max_area)
6. Persistence tracking (require N consecutive frames)

### Pipeline stages (detector.py process_frame)

1. Stabilisation (optional) - compensate for camera motion
2. Background subtraction - MOG2 adaptive model
3. Morphological cleaning - remove noise, fill gaps
4. Contour extraction - find candidate blobs
5. Size filtering - reject too small/large
6. Persistence filtering - require consistent tracks

## Configurable Parameters

Background Model (BackgroundConfig):
    history          Frames used for background model (default: 600)
    var_threshold    Variance threshold for foreground (default: 16)
    detect_shadows   Enable shadow detection (default: True)
    learning_rate    Adaptation speed, -1=auto (default: -1)

Stabilisation (StabiliserConfig):
    feature_detector ORB or AKAZE (default: ORB)
    max_features     Features to detect (default: 500)
    match_ratio      Lowe's ratio test threshold (default: 0.75)
    min_matches      Minimum matches for valid homography (default: 10)
    ransac_threshold RANSAC inlier threshold (default: 5.0)

Detection (MotionDetectorConfig):
    stabilisation_enabled  Enable frame stabilisation (default: True)
    min_area              Minimum blob area in pixels (default: 500)
    max_area              Maximum blob area in pixels (default: 5000)
    morph_kernel_size     Morphological kernel size (default: 5)
    morph_iterations      Morphological operation iterations (default: 2)

Persistence Tracking (TrackerConfig):
    persistence_enabled   Enable persistence filtering (default: True)
    min_persistence       Frames before emitting detection (default: 3)
    max_frames_missing    Frames before dropping track (default: 5)
    iou_threshold         Minimum IoU for matching (default: 0.3)

## Test Results Summary

Aquarium footage (10 videos, ~3000 frames, high activity density):

| Test Name          | Detections | Key Settings                           |
|--------------------|------------|----------------------------------------|
| tracking           | ~4,400     | defaults                               |
| tracking_parameters| 33,036     | sensitive: var=12, min_area=300        |
| tracking_tuned     | 11,396     | balanced: var=12, persistence=5        |
| anti_flicker       | 6,009      | strict: var=18, persistence=8, lr=0.001|

Observations:

- Lower var_threshold → more detections but more noise
- Persistence filtering effective at removing transient noise
- Disabling shadow detection helps with flicker
- Slow learning_rate (0.001) helps ignore rapid brightness changes
- Trade-off: sensitivity vs precision (tunable per use case)

## Class Reference

VideoMetadata       Container for video file properties
FrameContext        Metadata passed with each frame to detectors
VideoSource         Abstract base for video loaders
LocalVideoSource    Concrete implementation using OpenCV (local files)
S3VideoSource       Concrete implementation using OpenCV (S3 streaming)
Detection           Single detection result
DetectorBase        Abstract base for detection algorithms
MotionDetector      Motion detection using stabilisation + background subtraction
FrameStabiliser     Feature-based frame alignment (ORB/AKAZE)
BackgroundModel     Adaptive background subtraction (MOG2)
PersistenceTracker  Multi-frame tracking for noise filtering
TrackedObject       Single tracked object state
DetectionWriter     CSV output writer with single/per-video modes
DetectionPipeline   Main orchestrator connecting all components
PipelineConfig      Complete pipeline configuration
PipelineResult      Processing statistics and results
DryRunResult        Statistics from dry run scanning

## Architecture Notes

- Video sources are discovered externally via discover_*() functions
- Pipeline accepts List[VideoSource], agnostic to source type
- Detectors are pluggable via registry or factory function
- Design supports future parallelisation at the caller level
- Each component uses context managers for resource cleanup

## Notes

- Sample footage not fully representative; real tuning on AWS data
- Keep parameters configurable throughout
- Confidence field left blank for motion detection (for ML compatibility)
- Renamed 'pipeline' directory to 'engine'
- FrameContext lives in source module (created by source, consumed by detector)
- Source discovery separated from pipeline for flexibility (local, S3, etc.)
- Pipeline designed to be source-agnostic via VideoSource interface
- Aquarium footage useful for development but differs from sea deployment
  (high vs low activity density, different lighting conditions)
- For sparse deployment footage, prioritise precision over recall

## Usage Example

    # Command line (local files):
    python run_pipeline.py --input ./data/footage/ --output ./results/ -v

    # With config file:
    python run_pipeline.py --config config/default.yaml --input ./data/

    # Test with custom parameters:
    python tests/test_aquarium_visualisation.py \
        --num-videos 10 \
        --output-name my_test \
        --learning-rate 0.001 \
        --var-threshold 18 \
        --detect-shadows false \
        --min-area 450 \
        --min-persistence 8 \
        --max-frames-missing 2


    # Programmatic (local):
    from engine import discover_local_videos
    from pipeline import DetectionPipeline, PipelineConfig

    sources = discover_local_videos("./data/aws_footage/aquarium/", "*.ts")
    config = PipelineConfig()
    pipeline = DetectionPipeline(config)
    result = pipeline.process_sources(sources)
    print(result.summary())

    # Programmatic (S3):
    from engine import discover_s3_videos
    from pipeline import DetectionPipeline, PipelineConfig

    # First run: aws sso login --profile m3b-detector
    sources = discover_s3_videos(
        bucket="alga-field-processed-uploads",
        prefix="processed/{device}/video/cam-3-0/2025-11-26/",
        profile_name="m3b-detector"
    )
    config = PipelineConfig()
    pipeline = DetectionPipeline(config)
    result = pipeline.process_sources(sources)
    print(result.summary())

## Plans for Package Deployment

Assessment of deployment readiness for GitHub/cross-machine use.

Components Ready:
    ✅ Core pipeline          Working end-to-end
    ✅ Dependencies           environment.yml + requirements.txt
    ✅ CLI entry point        run_pipeline.py
    ✅ Config system          YAML config support
    ✅ S3 integration         SSO auth documented
    ✅ Logging                Configurable logging

Components Missing:
    | Component              | Priority | Effort   |
    |------------------------|----------|----------|
    | README.md              | High     | 30 min   |
    | .gitignore             | High     | 5 min    |
    | Hardcoded paths check  | High     | 10 min   |
    | Unit tests (pytest)    | Medium   | 2-4 hrs  |
    | pyproject.toml         | Low      | 30 min   |
    | License file           | Low      | 5 min    |
    | CI/CD (GitHub Actions) | Low      | 1 hr     |

Estimated time to deployable state: ~1 hour for essentials

README.md should include:
    - Project description
    - Installation instructions (conda + pip options)
    - Quick start guide
    - Usage examples (CLI + programmatic)
    - Configuration reference
    - AWS S3 setup instructions

.gitignore should exclude:
    - __pycache__/
    - *.pyc
    - test_output/
    - .env
    -*.egg-info/
    - .vscode/
    - *.log
