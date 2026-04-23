# Smoke Test
 
This document defines the smoke test procedure to be run before merging pull
requests to the `Main` branch. It has two parts:
 
1. **Automated tests** — run via `pytest`, cover all non-GUI logic
2. **Manual test checklist** — covers the full GUI interaction surface
 
Both must pass before a PR is accepted.
 
---

## Part 1: Automated tests
 
```bash
# Run the full GUI test suite
pytest tests/gui/ -v --tb=short
 
# Expected: all tests pass, zero failures
```
 
### What the automated tests cover
 
| Test file | Coverage |
|-----------|----------|
| `test_conversion.py` | `numpy_bgr_to_qimage` pixel format, data ownership, empty frames |
| `test_seekable_source.py` | Open, seek, read, metadata, frame count, edge cases |
| `test_detection_table_model.py` | Row/column counts, data roles, status column, append/remove, sorting |
| `test_validation_model.py` | Status changes, progress counting, next-unreviewed, manual detections, signals |
| `test_session_manager.py` | Save/load round-trip, export filtering, corrected geometry, manual detection persistence, AWS profile |
| `test_s3_cache.py` | Cache path generation, cache hits, download (mocked boto3) |
| `test_video_resolution.py` | Path resolution logic for local and S3 sources |
| `test_annotation_integration.py` | FrameAnnotator produces correct overlays |
 
### Adding tests for new features
 
Any new non-GUI logic (models, managers, utilities) must have corresponding
unit tests before the PR is merged. Use the existing fixtures in
`tests/gui/conftest.py` — particularly the `qapp` fixture (session-scoped
`QApplication` instance required by all Qt model tests).
 
 ---
 
## Part 2: Manual test checklist
 
### Prerequisites
 
Before starting, ensure:
 
- [ ] `pytest tests/gui/ -v` passes with zero failures
- [ ] You have a test detection CSV with detections across multiple videos
- [ ] You have the corresponding video files on disk
- [ ] (Optional) S3 access configured if testing cloud features

**NB:** Minimum test data is shipped with the package at tests/data/
 
Launch the GUI:
 
```bash
seavision-gui
```
 
---

### 1. Application launch
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 1.1 | Launch `seavision-gui` | Window opens, title is "SeaVision", Validation tab visible | ☐ |
| 1.2 | Verify empty state | Viewer shows placeholder text with open instructions, transport disabled, no crash | ☐ |
| 1.3 | Resize window | All panels scale, no clipping or crash | ☐ |
| 1.4 | Drag all splitter boundaries | Panels resize smoothly | ☐ |
 
---

### 2. Open single video (no CSV)
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 2.1 | File → Open Video (`Ctrl+O`) | File dialog opens | ☐ |
| 2.2 | Select a video file | Video opens, first frame displays | ☐ |
| 2.3 | Press Space | Playback starts at 10 FPS, frame counter advances | ☐ |
| 2.4 | Press Space again | Playback pauses | ☐ |
| 2.5 | Press Right arrow (×3) | Steps forward 3 frames, counter updates | ☐ |
| 2.6 | Press Left arrow | Steps back 1 frame | ☐ |
| 2.7 | Drag slider to middle | Video seeks to midpoint, correct frame shown | ☐ |
| 2.8 | Click slider near end | Seeks correctly | ☐ |
| 2.9 | Change speed to 2× | Playback visibly faster | ☐ |
| 2.10 | Change speed to 0.25× | Playback visibly slower | ☐ |

**NB:** Example video file ships with the package at "tests/data/detection_data/09-00-13.ts"

---
 
### 3. New session (CSV + videos)
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 3.1 | File -> New Session (`Ctrl+N`) | Prompted for CSV file | ☐ |
| 3.2 | Select CSV, then video directory | Session loads, video list populates | ☐ |
| 3.3 | Video list shows all videos | Each has detection count and "0/N reviewed" | ☐ |
| 3.4 | First video opens automatically | Frame displays with bounding box overlays | ☐ |
| 3.5 | Detection table populates | Correct columns: Frame, Time, Confidence, Label, Track, Status | ☐ |
| 3.6 | All statuses show `·` (pending) | No pre-set statuses | ☐ |
| 3.7 | Status bar shows progress | e.g. "video1.ts — 0/47 reviewed" | ☐ |
| 3.8 | Window title updates | Shows CSV filename | ☐ |
 
---
 
### 4. Detection navigation and selection
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 4.1 | Click a row in the detection table | Video seeks to that frame, detection highlighted in cyan | ☐ |
| 4.2 | Detail panel updates | Shows frame, time, confidence, size, label, track, status | ☐ |
| 4.3 | Click a different row | Video seeks, highlight moves, detail updates | ☐ |
| 4.4 | Click a detection box directly on the frame | Corresponding table row selects, detail updates | ☐ |
| 4.5 | Press `Ctrl+Right` | Jumps to next detection in the table | ☐ |
| 4.6 | Press `Ctrl+Left` | Jumps to previous detection in the table | ☐ |
| 4.7 | Press `N` | Jumps to next unreviewed detection | ☐ |
| 4.8 | Sort table by Confidence column | Rows reorder, clicking still seeks correctly | ☐ |
| 4.9 | Sort by Frame column | Rows return to frame order | ☐ |
 
---

### 5. Review actions
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 5.1 | Select a detection, press `C` | Status → `✓`, green tint in table, auto-advances | ☐ |
| 5.2 | Press `R` on next detection | Status → `✗`, red tint, auto-advances | ☐ |
| 5.3 | Press `S` on next detection | Status → `—`, grey tint, auto-advances | ☐ |
| 5.4 | Click Confirm button (mouse) | Same effect as `C` | ☐ |
| 5.5 | Click Reject button (mouse) | Same effect as `R` | ☐ |
| 5.6 | Click Skip button (mouse) | Same effect as `S` | ☐ |
| 5.7 | Status bar updates | Progress counts accurate after each action | ☐ |
| 5.8 | Video list sidebar updates | Progress indicator for current video increments | ☐ |
| 5.9 | Confirm all pending, press `N` | No more unreviewed — `N` does nothing or wraps | ☐ |
| 5.10 | `Shift+C` | All detections on current frame confirmed | ☐ |
| 5.11 | `Shift+R` on another frame | All detections on that frame rejected | ☐ |
| 5.12 | `N` exhausts current frame first | On a frame with 3 dets, confirm 1, press N — goes to 2nd on same frame | ☐ |
 
---
 
### 6. Filtering
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 6.1 | Set status filter to "Pending" | Only unreviewed detections visible | ☐ |
| 6.2 | Set status filter to "Confirmed" | Only confirmed visible | ☐ |
| 6.3 | Set status filter to "Rejected" | Only rejected visible | ☐ |
| 6.4 | Set status filter back to "All" | All detections visible, colours intact | ☐ |
| 6.5 | Set class filter to a specific label | Only matching label visible | ☐ |
| 6.6 | Combine status + class filters | Intersection shown | ☐ |
| 6.7 | Set status filter to "Manual" | Only manual detections visible (empty if none added) | ☐ |
 
---

### 7. Manual detection (add/remove)
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 7.1 | Press `A` | Add mode active, cursor → crosshair, status bar shows instruction | ☐ |
| 7.2 | Click and drag on frame | Bounding box drawn as you drag | ☐ |
| 7.3 | Release mouse | Label picker dialog appears with existing labels | ☐ |
| 7.4 | Select a label | Detection added to table: confirmed, italic, confidence "—" | ☐ |
| 7.5 | Verify add mode exited | Cursor returns to normal (one-shot mode) | ☐ |
| 7.6 | Detection visible on frame | New box rendered with confirmed colour | ☐ |
| 7.7 | Press `A`, draw, type a NEW label | New label accepted, appears in class filter dropdown | ☐ |
| 7.8 | Press `L` then draw | Detection created with last-used label, no dialog | ☐ |
| 7.9 | Select manual detection, press Delete | Detection removed from table and frame | ☐ |
| 7.10 | Select pipeline detection, press Delete | Nothing happens (pipeline dets can't be removed) | ☐ |
| 7.11 | Open plain video (no CSV), press `A`, draw | Text input appears, type label, detection added | ☐ |
 
---
 
### 8. Bounding box editing
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 8.1 | Select a detection (click box or table row) | 8 resize handles appear at corners and midpoints | ☐ |
| 8.2 | Drag the box body (not on a handle) | Box moves, clamped to frame bounds | ☐ |
| 8.3 | Release after move | Status → `✎` (corrected), detail panel shows new coords | ☐ |
| 8.4 | Drag a corner handle | Box resizes, minimum 10×10 px enforced | ☐ |
| 8.5 | Release after resize | Status → `✎`, geometry updated in detail panel | ☐ |
| 8.6 | No ghost rectangles or smear trails | Clean rendering during and after drag | ☐ |
| 8.7 | Consistent line width | Open 640×480 and 1920×1080 video — outlines look same thickness | ☐ |
 
---
 
### 9. Context menus
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 9.1 | Right-click on video frame (no selection) | Menu: Add Detection, Confirm All on Frame, Reject All on Frame | ☐ |
| 9.2 | Right-click with a detection selected | Additional: Change Label..., (Remove if manual) | ☐ |
| 9.3 | Change Label → pick new label | Table and detail panel update | ☐ |
| 9.4 | Right-click detection in table | Context menu with Confirm/Reject/Skip/Change Label options | ☐ |
 
---
 
### 10. Multi-video workflow
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 10.1 | Click a different video in the sidebar | Viewer switches, table repopulates, previous progress preserved | ☐ |
| 10.2 | Click back to first video | Previous review statuses still visible | ☐ |
| 10.3 | Review some detections in second video | Sidebar progress updates for that video | ☐ |
 
---
 
### 11. Session save/load
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 11.1 | File → Save Session (`Ctrl+S`) | Prompted for location (first save) | ☐ |
| 11.2 | Save completes | Title bar no longer shows `*` | ☐ |
| 11.3 | Make another change, press `Ctrl+S` | Saves silently to same file (no prompt) | ☐ |
| 11.4 | `Ctrl+Shift+S` (Save As) | Always prompts for new location | ☐ |
| 11.5 | Close and reopen GUI | — | ☐ |
| 11.6 | File → Load Session, select saved file | All progress restored: statuses, corrections, manual dets | ☐ |
| 11.7 | Status bar reports load stats | "N applied, M skipped" | ☐ |
| 11.8 | Corrected geometry restored | Boxes in corrected positions, `✎` status in table | ☐ |
 
---
 
### 12. Export
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 12.1 | File → Export (`Ctrl+E`) | Prompted for CSV save location | ☐ |
| 12.2 | Open exported CSV | Contains only CONFIRMED and CORRECTED detections | ☐ |
| 12.3 | Check `status` column | Values are CONFIRMED or CORRECTED | ☐ |
| 12.4 | Check `source` column | `pipeline` or `manual` as appropriate | ☐ |
| 12.5 | Corrected detections have updated geometry | xc/yc/width/height match the edited values | ☐ |
| 12.6 | Manual detections included | With source=manual, confidence blank | ☐ |
| 12.7 | Export with nothing confirmed | CSV has header row only, count = 0 | ☐ |
 
---
 
### 13. Unsaved changes protection
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 13.1 | Make a change (confirm a detection) | Title bar shows `*` | ☐ |
| 13.2 | Try to close the window | Dialog: Save / Don't Save / Cancel | ☐ |
| 13.3 | Click Cancel | Window stays open | ☐ |
| 13.4 | Click Don't Save | Window closes, changes lost | ☐ |
| 13.5 | Make changes, click Save in dialog | Session saved, then window closes | ☐ |
 
---

### 14. View menu and overlays
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 14.1 | View → Show Detections (uncheck) | All bounding boxes disappear | ☐ |
| 14.2 | Seek to a different frame | Still no boxes | ☐ |
| 14.3 | Re-check Show Detections | Boxes reappear in correct positions and colours | ☐ |
| 14.4 | View → Show Rejected Detections (uncheck) | Rejected boxes hidden, others remain | ☐ |
| 14.5 | Re-check Show Rejected | Rejected boxes reappear | ☐ |
 
---
 
### 15. Drag and drop
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 15.1 | Drag a `.csv` onto the window | Session flow starts (prompts for video dir) | ☐ |
| 15.2 | Drag a `.ts` file onto the window | Opens as plain video | ☐ |
| 15.3 | Drag a `.seavision-session` file | Session loads | ☐ |
 
---

### 16. S3 integration (if applicable)
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 16.1 | Open CSV with S3 URIs | Profile picker appears, no video dir prompt | ☐ |
| 16.2 | Select profile, proceed | Download progress bar, videos cached | ☐ |
| 16.3 | Re-open same session | Cache hit, no re-download | ☐ |
| 16.4 | S3 with no/expired credentials | Clear error message, no crash | ☐ |
| 16.5 | Tools → Clear Video Cache | Size shown, cache cleared | ☐ |
 
---
 
### 17. Window state persistence
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 17.1 | Resize window and move splitters | — | ☐ |
| 17.2 | Close and reopen | Window geometry and splitter positions restored | ☐ |
| 17.3 | Change playback speed to 2× | — | ☐ |
| 17.4 | Close and reopen | Speed dropdown still shows 2× | ☐ |
 
---
 
### 18. Error handling
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 18.1 | Open session with a missing video file | Warning per file, greyed in list, other videos work | ☐ |
| 18.2 | Open a corrupt/truncated video | Error message or black frame, no crash | ☐ |
| 18.3 | Load session referencing moved CSV | Error dialog with clear message | ☐ |
 
---
 
### 19. Regression — no thread leaks
 
| # | Step | Expected result | Pass? |
|---|------|----------------|-------|
| 19.1 | Open session, review detections, close | Process exits cleanly (no hanging) | ☐ |
| 19.2 | Open video, play, close mid-playback | Process exits cleanly | ☐ |
 
---

## PR acceptance criteria
 
A pull request to `Main` is ready to merge when:
 
1. ✅ `pytest tests/gui/ -v` — all tests pass
2. ✅ `pytest tests/gui/test_smoke.py -v` — smoke tests pass
3. ✅ Manual checklist sections 1–14 completed (core features)
4. ✅ Manual checklist sections 15–18 completed where applicable (S3, drag-drop, error handling)
5. ✅ Section 19 (no thread leaks) — process exits cleanly
6. ✅ No new `# TODO` items without a linked issue
 
Sections 15–16 (drag-and-drop, S3) may be marked N/A if the PR does not
touch those features, but must be run for any PR that modifies session
management, video loading, or S3-related code.
