# User Guide

This document covers every feature of the SeaVision Validation GUI in detail.
For a quick overview, see [Getting Started](getting-started.md).

---

## Window layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Menu bar: File  View  Tools  Help                                       │
├────────────┬──────────────────────────────────┬──────────────────────────┤
│            │                                  │   DETECTION TABLE        │
│  VIDEO     │                                  │   Frame | Conf | Status  │
│  LIST      │       VIDEO VIEWER               ├──────────────────────────┤
│            │                                  │   DETECTION DETAIL       │
│            │   (with bounding box overlays)   │   Frame, Time, Conf,     │
│            │                                  │   Size, Label, Track     │
│            ├──────────────────────────────────┤                          │
│            │  [<<] [<] [▸] [>] [>>]  ──o───── │  [Confirm][Reject][Skip] │
├────────────┴──────────────────────────────────┴──────────────────────────┤
│  Status bar                                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

All panel boundaries are **draggable splitters** — resize them to suit your
monitor. Splitter positions are saved between sessions via `QSettings`.

---

## Video list (left sidebar)

Shows every source video referenced in the loaded CSV. Each entry displays:

- Video filename
- Detection count (e.g. "47 detections")
- Review progress (e.g. "12/47 reviewed")
- Colour coding: grey = not started, yellow = in progress, green = complete

Click a video to switch to it. The viewer, detection table, and detail panel
all update. Your review progress on the previous video is preserved.

Videos whose files could not be found on disk are shown greyed out with a
warning icon. They can still be selected but no frames will display.

---

## Video viewer (centre)

Displays the current video frame with detection bounding boxes overlaid. The
viewer uses a `QGraphicsView` with interactive overlays, meaning you can:

- **Click** a detection box to select it (syncs with the table)
- **Drag** a detection box to reposition it (sets status to CORRECTED)
- **Drag a corner handle** to resize a detection (sets status to CORRECTED)
- **Right-click** the frame for a context menu with additional actions

### Detection box colours

| Colour | Meaning |
|--------|---------|
| Red | Pending (unreviewed) |
| Green | Confirmed |
| Grey | Rejected |
| Blue/Cyan | Currently selected |
| Orange | Corrected geometry |

When "Show Rejected Detections" is disabled (View menu), rejected detection
boxes are hidden entirely.

### Zoom and fit

The frame automatically scales to fit the viewer widget. When you resize the
window or drag splitters, the frame rescales to fill the available space while
preserving aspect ratio.

---

## Detection table (right, top)

A sortable table showing all detections for the current video. Columns:

| Column | Description |
|--------|-------------|
| Frame | Frame number in the video |
| Time | Timestamp (calculated from frame number and FPS) |
| Confidence | Detection confidence score (blank for manual detections) |
| Label | Detection class label |
| Track | Tracker-assigned ID (if tracking was enabled) |
| Status | Review status symbol |

### Status symbols

| Symbol | Meaning |
|--------|---------|
| `·` | Pending |
| `✓` | Confirmed |
| `✗` | Rejected |
| `—` | Skipped |
| `✎` | Corrected (geometry edited) |

### Sorting

Click any column header to sort. Click again to reverse. Sorting does not
affect the underlying data or the order of keyboard navigation.

### Filtering

Two filter dropdowns sit above the table:

- **Status filter** — All, Pending, Confirmed, Rejected, Skipped, Corrected, Manual
- **Class filter** — All, or any specific label from the dataset

Filters combine: selecting "Pending" + "seal" shows only unreviewed seal
detections.

### Row selection

Clicking a row in the table:

1. Seeks the video to that detection's frame
2. Highlights the selected detection with a distinct colour in the viewer
3. Updates the detection detail panel
4. Enables the review action buttons

### Context menu (right-click on a table row)

- **Confirm** / **Reject** / **Skip** — same as buttons/keyboard
- **Change Label...** — pick a new label from existing classes or type a new one
- **Remove** — delete a manually-added detection (disabled for pipeline detections)
- **Confirm All on Frame** — confirm every detection on this frame
- **Reject All on Frame** — reject every detection on this frame

---

## Detection detail panel (right, bottom)

Shows full metadata for the currently selected detection:

- Frame number and timestamp
- Current status
- Confidence score
- Bounding box size (width × height in pixels)
- Centre coordinates (xc, yc)
- Label and track ID
- Corrected geometry (if edited)

---

## Review actions

### Buttons

Three buttons below the detail panel:

- **Confirm** — mark the detection as a true positive
- **Reject** — mark it as a false positive
- **Skip** — defer the decision

All three are also available as keyboard shortcuts (see
[Keyboard Shortcuts](keyboard-shortcuts.md)).

### Auto-advance

After pressing Confirm, Reject, or Skip, the selection automatically advances
to the next unreviewed detection. If there are more unreviewed detections on
the same frame, they are visited first before moving to another frame.

### Batch actions

- **`Shift+C`** — Confirm all detections on the current frame
- **`Shift+R`** — Reject all detections on the current frame

These are useful for frames with many obvious true or false positives.

---

## Adding manual detections

If the pipeline missed a detection, you can add one manually:

1. Press **`A`** to enter add mode (cursor becomes a crosshair)
2. **Click and drag** on the video frame to draw a bounding box
3. Release the mouse — a label picker dialog appears
4. Select an existing label or type a new one
5. The detection is added to the table with status CONFIRMED

Add mode is **one-shot**: after drawing one box, it exits automatically.
Press `A` again to draw another.

### Quick-add with last label

Press **`L`** to enter add mode with the same label as the selected detection
pre-selected. When you draw a box, it is created immediately with that label — 
no dialog needed.

### Removing manual detections

Select a manual detection in the table, then press **Delete** or use the
right-click context menu → Remove. Only manually-added detections can be
removed; pipeline detections can only be rejected.

---

## Bounding box editing

Select a detection in the viewer (click its box or select its table row):

- **Move**: click and drag the box body to reposition
- **Resize**: drag any of the 8 handles (corners + edge midpoints)
- Boxes are clamped to the frame boundaries
- Minimum size is 10×10 pixels

After editing, the detection status changes to **CORRECTED** and the detail
panel shows the updated geometry. The original pipeline geometry is preserved
internally and can be restored by rejecting and re-confirming the detection.

Corrected geometry is saved in session files and used in exports.

---

## Transport bar (bottom)

| Control | Action |
|---------|--------|
| `⏮` | Jump to first frame |
| `◀` | Step back one frame |
| `▶` / `⏸` | Play / Pause |
| `▶▏` | Step forward one frame |
| `⏭` | Jump to last frame |
| Slider | Seek to any frame (drag or click) |
| Speed dropdown | Playback speed: 0.25×, 0.5×, 1×, 2×, 5× |

Frame number and timestamp are displayed next to the slider.

### Detection navigation buttons

| Button | Action |
|--------|--------|
| `⏪ Det` | Jump to previous detection's frame |
| `Det ⏩` | Jump to next detection's frame |

---

## Playback

Press **Space** to toggle play/pause. During playback, detection overlays are
rendered on each frame in real time using the `FrameAnnotator`. The selected
detection (if any) remains highlighted.

Playback speed can be changed from the speed dropdown on the transport bar.
The speed setting is saved across sessions.

---

## Session management

### Save session (`Ctrl+S`)

Saves all review decisions, geometry corrections, and manual detections to a
`.seavision-session` file (JSON format). On first save, you are prompted for a
file location. Subsequent saves go to the same file silently.

### Save As (`Ctrl+Shift+S`)

Always prompts for a new file location.

### Load session (File → Load Session)

Opens a previously saved `.seavision-session` file. The original CSV and video
files must still be accessible at their original paths (or the video directory
must be re-specified). All review progress is restored.

### Export (`Ctrl+E`)

Writes a new CSV containing only **confirmed** and **corrected** detections.
The exported CSV includes:

- All original columns from the pipeline CSV
- A `status` column (`CONFIRMED` or `CORRECTED`)
- A `source` column (`pipeline` or `manual`)
- Corrected geometry values where applicable

The original pipeline CSV is never modified.

### Unsaved changes

If you have unsaved changes and try to close the window or open a new session,
a dialog asks: **Save / Don't Save / Cancel**. The window title shows an
asterisk (`*`) when there are unsaved changes.

---

## View menu options

| Option | Description |
|--------|-------------|
| Show Detections | Toggle all detection overlays on/off |
| Show Rejected Detections | Toggle visibility of rejected detection boxes |
| *Overlay Settings...* | Configure box thickness, colours, label visibility, font size, confidence threshold |

**NB:** Overlay settings are not yet implemented - these are coming soon.

Overlay settings are persisted across sessions via `QSettings`.

---

## Tools menu

| Option | Description |
|--------|-------------|
| Set Video Cache Location | Set the directory where videos downloaded from S3 buckets are cached. Defaults to: ~/.seavision/cache/|
| Clear Video Cache | Remove cached S3 video downloads (shows size before clearing) |
| AWS Status | Show current AWS credential state and expiry |

**NB:** AWS status not yet implemented - coming soon.

---

## Drag and drop

You can drag files onto the main window:

| File type | Action |
|-----------|--------|
| `.csv` | Opens the session flow (prompts for video directory) |
| `.ts`, `.mp4`, `.avi`, etc. | Opens as a plain video |
| `.seavision-session` | Loads the saved session |
 
---

## Window title

The title bar reflects the current state:

| State | Title |
|-------|-------|
| No session | `SeaVision` |
| Session loaded | `SeaVision — detections.csv` |
| Unsaved changes | `SeaVision — detections.csv *` |

---

## Status bar

The status bar at the bottom shows contextual information:

- **During review**: `video2.ts — 12/47 reviewed — 8 confirmed, 3 rejected, 1 manual`
- **During add mode**: `Click and drag on the frame to add a detection`
- **During S3 download**: Download progress per file
