# Troubleshooting
 
## Installation issues
 
### PySide6 DLL errors (Windows)
 
If you see an `ImportError` mentioning DLL files, this usually means a
conflicting Qt installation. Uninstall any other Qt packages:
 
```bash
pip uninstall PyQt5 PyQt6
pip install --force-reinstall PySide6
```
 
### `seavision-gui` command not found
 
Ensure the package was installed with the GUI extra:
 
```bash
pip install -e ".[gui]"
```
 
Check that the `seavision-gui` entry point was created:
 
```bash
which seavision-gui  # Linux/macOS
where seavision-gui  # Windows
```
 
---
 
## Video playback issues
 
### Seeking is inaccurate on .ts files
 
`.ts` (transport stream) files lack clean keyframe indices. The GUI
automatically preloads these files into memory for accurate seeking. If you
see incorrect frames after seeking, verify that preloading is enabled (check
the status bar for "preloading..." on video open).
 
For very large `.ts` files that exceed available RAM, consider converting to
`.mp4` first:
 
```bash
ffmpeg -i input.ts -c copy output.mp4
```
 
### Black frames or "Frame decode error"
 
This usually indicates a corrupt or truncated video file. The GUI logs
warnings for individual corrupt frames and continues playback. If the entire
video shows black, the file may be unreadable by OpenCV.
 
### Playback stutters
 
Ensure no other CPU-intensive processes are competing. You can also reduce
playback speed from the transport bar dropdown.
 
---
 
## Session and data issues
 
### "N applied, M skipped" when loading a session
 
Skipped decisions occur when the session file references detections that no
longer exist in the CSV (e.g. the CSV was regenerated with different
parameters). This is expected and logged as warnings.
 
### Export produces an empty CSV
 
Export only includes CONFIRMED and CORRECTED detections. If you have only
rejected or skipped detections, the CSV will contain only the header row.
 
### Session file won't load — videos not found
 
The session stores absolute paths. If videos have been moved, you will be
prompted to re-specify the video directory. For S3 sessions, ensure
credentials are still valid.
 
---
 
## Display issues
 
### Detection boxes don't appear
 
Check **View → Show Detections** is enabled. Also verify the confidence
threshold in **View → Overlay Settings** isn't filtering out your detections.
 
### Window opens very small or off-screen
 
Delete the saved geometry settings:
 
- **Linux**: `~/.config/SeaVision/SeaVision.conf`
- **macOS**: `~/Library/Preferences/com.SeaVision.SeaVision.plist`
- **Windows**: Registry key `HKEY_CURRENT_USER\Software\SeaVision\SeaVision`
 
---
 
## Getting more information
 
Run with debug logging for detailed diagnostic output:
 
```bash
seavision-gui --log-level DEBUG
```
