# Architecture
 
This document describes the internal structure of the GUI for developers who
need to modify or extend it.
 
---
 
## Package structure
 
```
seavision/gui/
├── __init__.py
├── app.py                          # QApplication, main() entry point
├── main_window.py                  # QMainWindow, menu bar, tab container
├── shared/
│   ├── __init__.py
│   ├── conversion.py               # numpy BGR → QImage/QPixmap helpers
│   └── session_utils.py            # resolve_video_paths (pure logic)
└── validation/
    ├── __init__.py
    ├── button_styles.py            # Style sheets for action buttons
    ├── detection_detail.py         # DetectionDetailPanel - displays details for selected detection
    ├── detection_rect_item.py      # QGraphicsRectItem — draggable bounding box
    ├── detection_table.py          # DetectionTableModel + DetectionTableView
    ├── interactive_frame_view.py   # QGraphicsView — replaces old FrameDisplay
    ├── interactive_frame_scene.py  # QGraphicsScene — detection overlay management
    ├── s3_browser.py               # S3BrowserDialog — bucket browser UI
    ├── seekable_source.py          # SeekableVideoSource — cv2 random-access wrapper
    ├── session.py                  # SessionManager — save/load/export (no Qt)
    ├── tab.py                      # ValidationTab — assembles all sub-widgets
    ├── transport_bar.py            # TransportBar — playback controls + slider
    ├── validation_model.py         # ValidationModel — mutable detection state
    ├── video_cache.py              # S3VideoCache
    ├── video_list.py               # VideoListWidget — sidebar with progress
    ├── video_viewer.py             # FrameDisplay (QLabel)
    └── video_worker.py             # VideoDecoderWorker (runs on QThread)
```
 
---

## Data flow
 
```
CSV file ──→ CSVDetectionLoader ──→ ValidationModel
                                         │
Video file ──→ SeekableVideoSource       │
                    │                    │
                    ▼                    ▼
             VideoDecoderWorker ←── (frame_number, detections)
                    │
                    │ annotate via FrameAnnotator
                    ▼
               QImage signal ──→ InteractiveFrameView
```

### The ValidationModel is the single source of truth
 
`ValidationModel` wraps raw `Detection` objects from the CSV loader with a
mutable `ValidatedDetection` wrapper that adds:
 
- `status` — `PENDING`, `CONFIRMED`, `REJECTED`, `SKIPPED`, `CORRECTED`
- `corrected_geometry` — optional dict with `xc`, `yc`, `width`, `height`
- `is_manual` — whether this detection was added by the reviewer
- `id` — unique integer for the lifetime of the model
 
Every widget reads from or writes to the model. When state changes, the model
emits signals that all connected widgets listen to:
 
- `detection_status_changed(detection_id, new_status)` — a detection was reviewed
- `progress_changed(progress_dict)` — review counts updated
- `detection_added(validated_detection)` — a manual detection was created
- `detection_removed(detection_id)` — a manual detection was deleted
 
---

---
 
## Threading model
 
There are exactly **two threads**:
 
### Main thread
 
Owns all widgets, handles all user input, updates all displays. This is a hard
Qt requirement — widgets must only be touched from the main thread.
 
### Video worker thread
 
Handles `cv2.VideoCapture` operations (open, seek, read) and frame annotation
via `FrameAnnotator`. Communicates with the main thread exclusively through
**Qt signals**, which are automatically queued across thread boundaries.
 
Key signals crossing the thread boundary:
 
| Direction | Signal | Payload |
|-----------|--------|---------|
| Main → Worker | `request_open(path, preload)` | Video file path |
| Main → Worker | `request_frame(frame_number)` | Seek target |
| Main → Worker | `start_playback()` | Begin continuous decode |
| Worker → Main | `frame_ready(QImage, frame_num, timestamp)` | Decoded frame |
| Worker → Main | `video_opened(VideoMetadata)` | File metadata |
 
The worker uses `QTimer.singleShot` for non-blocking playback loops — never
`while` + `sleep`.
 
---
 
## Engine components reused by the GUI
 
| Component | How the GUI uses it |
|-----------|-------------------|
| `CSVDetectionLoader` | Parses detection CSV files into `Detection` objects |
| `FrameAnnotator` | Draws bounding boxes onto video frames |
| `Detection` dataclass | The fundamental data unit; `ValidationModel` wraps these |
| `FrameContext` | Created by `SeekableVideoSource`, passed to `FrameAnnotator` |
| `VideoMetadata` | Drives transport bar range, time display, video list metadata |
 
Components **not** reused: `LiveVisualiser`, `PostHocVisualiser`,
`VideoWriterHandle`, `DetectionWriter`, and the pipeline itself. These are
forward-processing, write-once components incompatible with the GUI's
random-access, mutable workflow.
 
---
 
## Video source strategy
 
The GUI always validates against **local video files**. S3 videos are
downloaded to a local cache (`~/.seavision/cache/`) before validation begins.
This is a deliberate design decision: the validation workflow requires
random-access seeking (jumping between arbitrary frames dozens of times per
minute), which is too slow over HTTP.
 
`SeekableVideoSource` only handles local filesystem paths. S3 complexity is
isolated in `S3VideoCache`, which downloads files transparently during session
opening.
 
### Preloading
 
For `.ts` files (which have unreliable keyframe indices in OpenCV),
`SeekableVideoSource` can preload all frames into memory. This trades memory
for perfect seek accuracy.
 
---
 
## QGraphicsView display system
 
The video viewer uses `QGraphicsView` / `QGraphicsScene` instead of a plain
`QLabel`. This enables interactive bounding box editing:
 
- `InteractiveFrameScene` manages a pixmap background item plus
  `DetectionRectItem` instances for each detection on the current frame
- `DetectionRectItem` is a `QGraphicsRectItem` subclass with 8 resize handles,
  drag support, and geometry-change callbacks
- `InteractiveFrameView` handles fit-to-widget scaling via `fitInView`
 
Three coordinate systems are in play: **item-local** (each rect item's own
origin), **scene** (frame pixel coordinates), and **view** (widget screen
pixels). Use `mapToScene` / `mapFromScene` when converting between them.
 
---
 
## Test structure
 
```
tests/gui/
├── conftest.py                    # QApplication fixture (session-scoped)
├── test_conversion.py             # numpy → QImage helpers
├── test_seekable_source.py        # Video seek/read
├── test_detection_table_model.py  # Table model data/row/column
├── test_validation_model.py       # Status changes, progress, manual dets
├── test_session_manager.py        # Save/load/export round-trips
├── test_s3_cache.py               # S3 download cache (mocked boto3)
├── test_video_resolution.py       # Path resolution logic
└── test_annotation_integration.py # FrameAnnotator integration
```
 
Non-GUI logic (`SessionManager`, `ValidationModel`, `S3VideoCache`,
`resolve_video_paths`) is fully unit-tested. Widget-level testing is done
via the [Smoke Test](./Smoke%20test.md).