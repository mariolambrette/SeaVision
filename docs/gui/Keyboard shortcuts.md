# Keyboard Shortcuts

All shortcuts are active when the Validation tab has focus.

## Review actions

| Key | Action |
|-----|--------|
| `C` or `1` | Confirm selected detection |
| `R` or `2` | Reject selected detection |
| `S` or `3` | Skip selected detection |
| `Shift+C` | Confirm all detections on current frame |
| `Shift+R` | Reject all detections on current frame |

## Navigation

| Key | Action |
|-----|--------|
| `N` | Next unreviewed detection |
| `Space` | Play / Pause |
| `Left` | Previous frame |
| `Right` | Next frame |
| `Ctrl+Left` | Previous detection |
| `Ctrl+Right` | Next detection |

## Editing

| Key | Action |
|-----|--------|
| `A` | Enter add mode (draw a new detection) |
| `L` | Add detection with last-used label (no dialog) |
| `Delete` | Remove selected manual detection |

## Panning

| Key | Action |
|-----|--------|
| `Shift+Left` | Pan left on the frame when zoomed in |
| `Shift+Right` | Pan right on the frame when zoomed in |
| `Shift+Up` | Pan up on the frame when zoomed in |
| `Shift+Down` | Pan down on the frame when zoomed in |


## File operations

| Key | Action |
|-----|--------|
| `Ctrl+O` | Open video |
| `Ctrl+Shift+O` | Open session (CSV + videos) |
| `Ctrl+S` | Save session |
| `Ctrl+Shift+S` | Save session as... |
| `Ctrl+E` | Export confirmed detections |

## Tips for fast reviewing

The fastest workflow uses just three keys in a loop:

1. **`N`** — jump to next unreviewed detection
2. Look at the frame
3. **`C`** or **`R`** — confirm or reject

This allows processing one detection every 2–3 seconds.