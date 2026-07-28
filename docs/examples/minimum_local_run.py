"""
This is an example python script which demonstrated the minimum code required to
run a SeaVision detector (in this example, a YOLODetector) on videos stored on
the local machine.

The script discovers the videos, produces detections and saves them into a CSV 
file which can be interrogated using the SeaVision GUI.
"""

import seavision.engine as sv
from seavision.engine.detectors.yolo import YOLODetector, YOLODetectorConfig

# Path to the YOLO model weights
WEIGHTS = "./model.pt"

# Path to the locally stored videos
VIDEO_DIR = "./videos"
# File extension for the video files
VID_EXT = "*.mp4"

# Path where the detections should be saved
OUTPUT_DIR = "./output"

def main():
    """Minimal SeaVision detection run."""

    # Discover sources
    sources = sv.source.discover_local_videos(
        path = VIDEO_DIR,
        pattern = VID_EXT,
    )

    # Prepare detector
    detector_config = YOLODetectorConfig(
        model_path=WEIGHTS,
        device="cuda",
        conf_threshold=0.2,
    )

    # Prepare writer
    writer_config = sv.CSVWriterConfig(
        output_dir=OUTPUT_DIR,
        output_mode=sv.OutputMode.SINGLE_FILE,
        overwrite=True,
    )

    all_detections = []

    with YOLODetector(detector_config) as detector:
        for source in sources:
            for frame, context in source.iter_frames():
                detections = list(detector.process_frame(frame, context))
                all_detections.extend(detections)


    with sv.DetectionWriter(writer_config) as writer:
        for detection in all_detections:
            writer.write(detection)


if __name__ == "__main__":
    main()
