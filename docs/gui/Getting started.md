# Getting Started
 
## Prerequisites
 
- Python 3.10+
- The SeaVision package installed with GUI extras: `pip install -e ".[gui]"`
- PySide6 (installed automatically with the `[gui]` extra)
- OpenCV (`opencv-python`, also included)
- For videos stored in S3 buckets: `boto3` and configured AWS credentials

Verify the install:
 
```bash
seavision-gui
```
 
A window titled **SeaVision** should appear with an empty Validation tab.
 
If you get an `ImportError` mentioning PySide6, run:
 
```bash
pip install PySide6
```
 
If the error mentions DLL files (Windows), see [Troubleshooting](troubleshooting.md#pyside6-dll-errors).
 
---

## Opening your first session
 
A "session" pairs a **detection CSV** (output from the SeaVision pipeline)
with the **source video files** that the detections were drawn from.
 
1. **File → Open Session** (or `Ctrl+Shift+O`)
2. Select the detection CSV file
3. Select the directory containing the video files referenced in the CSV
4. The GUI loads all detections, populates the video list sidebar, and opens
   the first video
 
You should now see:
 
- **Left sidebar** — list of videos with detection counts
- **Centre** — video frame with detection bounding boxes overlaid
- **Right panel** — detection table (top) and detection detail (bottom)
- **Bottom** — transport bar with playback controls
- **Status bar** — current video name and progress counts
 
---

## Opening a single video (no CSV)
 
For quick inspection without a detection CSV:
 
1. **File → Open Video** (or `Ctrl+O`)
2. Select a `.ts`, `.mp4`, or `.avi` file
3. The video opens in the viewer with transport controls active
 
You can still manually add detections in this mode (press `A` to enter add
mode), but there is no detection table or session management until a CSV is
loaded.
 
---

## The review workflow
 
The fastest way to work through detections:
 
1. Press **`N`** to jump to the next unreviewed detection
2. Look at the frame — is the bounding box on a real object?
3. Press **`C`** to confirm, **`R`** to reject, or **`S`** to skip
4. The selection auto-advances to the next unreviewed detection
5. Repeat
 
A practised reviewer can process a detection every 2–3 seconds using this
keyboard-driven flow.
 
---

## Saving your work
 
- **`Ctrl+S`** — Save session (prompts for a location on first save)
- **`Ctrl+Shift+S`** — Save As (always prompts)
- **File → Export** (`Ctrl+E`) — Export confirmed detections to a new CSV
 
Session files use the `.seavision-session` extension and store all review
decisions, geometry corrections, and manually added detections. You can close
the GUI and resume later by opening the session file via **File → Load
Session**.
 
---

## Next steps
 
- [User Guide](user-guide.md) — detailed coverage of every feature
- [Keyboard Shortcuts](keyboard-shortcuts.md) — printable quick-reference
- [S3 & AWS Integration](s3-integration.md) — working with cloud-stored videos