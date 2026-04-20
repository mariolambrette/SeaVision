# Session File Format
 
Session files use the `.seavision-session` extension and contain JSON.
 
## Schema
 
```json
{
    "version": 1,
    "csv_path": "/path/to/detections.csv",
    "video_dir": "/path/to/videos/",
    "aws_profile": "m3b-detector",
    "timestamp": "2025-06-15T14:30:00Z",
    "decisions": {
        "video.ts::47::0": {
            "status": "CONFIRMED",
            "corrected_geometry": null,
            "is_manual": false
        },
        "video.ts::47::1": {
            "status": "REJECTED",
            "corrected_geometry": null,
            "is_manual": false
        },
        "video.ts::52::0": {
            "status": "CORRECTED",
            "corrected_geometry": {
                "xc": 325.0,
                "yc": 242.0,
                "width": 65.0,
                "height": 58.0
            },
            "is_manual": false
        }
    },
    "manual_detections": [
        {
            "source_file": "video.ts",
            "frame_number": 52,
            "timestamp": 5.2,
            "xc": 320.0,
            "yc": 240.0,
            "width": 60.0,
            "height": 60.0,
            "label": "seal",
            "status": "CONFIRMED",
            "corrected_geometry": null
        }
    ]
}
```
 
## Field reference
 
### Top-level fields
 
| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Schema version (currently `1`) |
| `csv_path` | string | Absolute path to the detection CSV used to create the session |
| `video_dir` | string | Absolute path to the video directory (or empty for S3-only) |
| `aws_profile` | string \| null | AWS profile used for S3 access, if applicable |
| `timestamp` | string | ISO 8601 UTC timestamp of when the session was saved |
| `decisions` | object | Map of decision keys to review decisions |
| `manual_detections` | array | List of manually added detections |
 
### Decision keys
 
Keys follow the format `{source_file}::{frame_number}::{index}` where
`index` is the detection's position within its frame among all pipeline
detections. This is deterministic for a given CSV because `CSVDetectionLoader`
loads in file order.
 
Only **non-PENDING** detections are saved. PENDING is the default state and
does not need to be persisted. The frame index counter increments for all
pipeline detections regardless of status to ensure key stability on reload.
 
### Decision values
 
| Field | Type | Description |
|-------|------|-------------|
| `status` | string | One of: `CONFIRMED`, `REJECTED`, `SKIPPED`, `CORRECTED` |
| `corrected_geometry` | object \| null | If corrected: `{xc, yc, width, height}` |
| `is_manual` | bool | Always `false` for pipeline detections |
 
### Manual detection entries
 
Manual detections store their full geometry and label because they do not
exist in the original CSV. See the schema example above for all fields.
 
## Compatibility
 
When loading a session, unknown decision keys (detections that no longer exist
in the CSV) are silently skipped and logged as warnings. This handles the case
where a CSV is regenerated with different detection parameters.