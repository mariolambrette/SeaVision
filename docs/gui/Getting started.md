# Getting Started

## Prerequisites


You must have installed the SeaVision package with GUI extras in a suitable
Python environment. For details see [here](.docs/Start_Here.md)

Verify the install:

```bash
seavision-gui
```

A window titled **SeaVision** should appear with an empty Validation tab.

If you get an `ImportError` mentioning PySide6, run:

```bash
pip install PySide6
```

If the error mentions DLL files (Windows), see [Troubleshooting](./Troubleshooting.md#pyside6-dll-errors).

---

## Opening your first session

A session pairs:

- A **detection CSV** (output from the SeaVision pipeline)
- The **source video files** that detections were created from

1. **File -> New Session** (or `Ctrl+N`)
2. Select the detection CSV file
3. Select the directory containing the video files referenced in the CSV
4. The GUI loads detections, populates the video list, and opens the first video

You should now see:

- **Left sidebar**: list of videos with detection counts
- **Center**: video frame with detection bounding boxes
- **Right panel**: detection table (top) and detection details (bottom)
- **Bottom**: transport bar with playback controls
- **Status bar**: current video and review progress

---

## Opening a single video (no CSV)

For quick inspection without a detection CSV:

1. **File -> Open Video** (or `Ctrl+O`)
2. Select a `.ts`, `.mp4`, or `.avi` file
3. The video opens in the viewer with transport controls active

You can still manually add detections in this mode (press `A` to enter add
mode), but there is no detection table or session management until a CSV is
loaded.

---

## Fast review workflow

1. Press **`N`** to jump to the next unreviewed detection
2. Check whether the box is on a real object
3. Press **`C`** to confirm, **`R`** to reject, or **`S`** to skip
4. The selection auto-advances to the next unreviewed detection
5. Repeat

A practiced reviewer can process a detection every 2 to 3 seconds using this
keyboard-driven flow.

---

## Saving your work

- **`Ctrl+S`**: Save session (prompts for a location on first save)
- **`Ctrl+Shift+S`**: Save As (always prompts)
- **File -> Export** (`Ctrl+E`): Export confirmed detections to a new CSV

Session files use the `.seavision-session` extension and store all review
decisions, geometry corrections, and manually added detections. You can close
the GUI and resume later by opening the session file via **File -> Load Session**.

---

## Next steps

- [User Guide](./User%20guide.md): detailed coverage of every feature
- [Keyboard Shortcuts](./Keyboard%20shortcuts.md): quick reference
- [S3 and AWS Integration](./S3%20Integration.md): working with cloud-stored videos
