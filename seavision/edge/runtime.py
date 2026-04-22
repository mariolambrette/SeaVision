"""SeaVision edge inference runtime.

This is the main class deployed to edge devices. It reads frames from a
capture source (camera or video file), runs ONNX inference, writes
detections to CSV, and optionally records periodic validation clips.

Dependencies:
    - onnxruntime (inference)
    - opencv-python-headless (frame capture, preprocessing, NMS)
    - numpy < 2.0 (array operations — numpy 2.0+ crashes on Pi 4)

Does NOT depend on:
    - ultralytics
    - torch / torchvision
    - PySide6

Usage:
    from seavision.edge import EdgeRuntime, EdgeConfig

    config = EdgeConfig.from_file("config.json")
    runtime = EdgeRuntime(config)
    runtime.run()
"""

import logging
import os
import time
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime

import cv2
import numpy as np
import onnxruntime as ort

from seavision import __version__

from .capture import CaptureError, FrameCapture
from .config import ARTIFACT_MANIFEST_FILENAME, ArtifactManifest, EdgeConfig
from .postprocess import postprocess, preprocess, scale_boxes_to_original
from .writer import EdgeDetectionWriter

logger = logging.getLogger(__name__)


def _parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _version_satisfies(version: str, version_range: str) -> bool:
    if not version_range:
        return True

    current = _parse_version(version)
    for raw_clause in version_range.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue

        operator = None
        for candidate in (">=", "<=", "==", ">", "<"):
            if clause.startswith(candidate):
                operator = candidate
                break

        if operator is None:
            raise ValueError(f"Unsupported version range clause: {clause}")

        target = _parse_version(clause[len(operator):].strip())
        if operator == ">=" and not (current >= target):
            return False
        if operator == "<=" and not (current <= target):
            return False
        if operator == ">" and not (current > target):
            return False
        if operator == "<" and not (current < target):
            return False
        if operator == "==" and not (current == target):
            return False

    return True


class EdgeRuntime:
    """
    Lightweight ONNX inference runtime for edge deployment.

    This class orchestrates the full inference pipeline on an edge device:

    1. Load the ONNX model into an ONNX Runtime session.
    2. Open the video source (camera or file)
    3. For each frame: preprocess -> infer -> postprocess -> write.
    4. Optionally record short validation clips at regular intervals.

    The runtime is designed to run continuously (for camera sources) or until
    the source is exhausted (for video files). It handles cleanup on both
    normal exit and interruption (CTRL+C).
    """

    def __init__(self, config: Optional[EdgeConfig] = None):
        """
        Initilaise the runtime.

        Args:
            config: Runtime configuration. If None, defaults are used.
        """
        self.config = config or EdgeConfig()

        self._session: Optional[ort.InferenceSession] = None
        self._input_name: Optional[str] = None
        self._capture: Optional[FrameCapture] = None
        self._writer: Optional[EdgeDetectionWriter] = None

        # Validation clip state
        self._clip_writer: Optional[cv2.VideoWriter] = None
        self._clip_frame_count: int = 0
        self._last_clip_time: float = 0.0

    @staticmethod
    def _sha256_for_file(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _validate_artifact(self) -> None:
        """Validate the artifact manifest, required files, and checksums."""
        if not self.config.artifact_dir:
            return

        artifact_dir = Path(self.config.artifact_dir)
        manifest = ArtifactManifest.from_file(
            artifact_dir / ARTIFACT_MANIFEST_FILENAME
        )

        if not _version_satisfies(__version__, manifest.runtime_version_range):
            raise ValueError(
                "Artifact runtime compatibility check failed: "
                f"SeaVision {__version__} does not satisfy "
                f"{manifest.runtime_version_range}"
            )

        for label, file_entry in {
            "model": manifest.model,
            "runtime_config": manifest.runtime_config,
            "export_metadata": manifest.export_metadata,
        }.items():
            file_path = artifact_dir / file_entry.path
            if not file_path.exists():
                raise FileNotFoundError(
                    f"Artifact {label} file is missing: {file_path}"
                )

            if file_entry.sha256:
                actual_sha256 = self._sha256_for_file(file_path)
                if actual_sha256 != file_entry.sha256:
                    raise ValueError(
                        f"Artifact {label} checksum mismatch for {file_path}: "
                        f"expected {file_entry.sha256}, got {actual_sha256}"
                    )

    def _load_model(self) -> None:
        """
        Load the ONNX model into an inference session.

        Configures ONNX runtime with settings optimised for edge hardware.
        """
        model_path = self.config.model_path

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model file not found: {model_path}. "
                f"Ensure the deployment bundle was extracted correctly."
            )
        
        sess_options = ort.SessionOptions()

        # Graph optimisation.
        if self.config.ort_optimization == "basic":
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            )
        else:
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )

        # Thread count — 0 means "all cores"
        threads = self.config.ort_threads
        if threads <= 0:
            import multiprocessing
            threads = multiprocessing.cpu_count()
        sess_options.intra_op_num_threads = threads

        logger.info(
            "Loading ONNX model: %s (threads=%d, optimization=%s)",
            model_path, threads, self.config.ort_optimization,
        )

        self._session = ort.InferenceSession(
            model_path, sess_options,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name

        logger.info("Model loaded successfully")

    def _open_capture(self) -> None:
        """Open the video source."""
        self._capture = FrameCapture(self.config.source)

    def _open_writer(self) -> None:
        """Open the detection CSV writer."""
        source_name = self.config.source
        # Use just the filename for video files, or "camera_N" for devices
        try:
            int(source_name)
            source_name = f"camera_{source_name}"
        except ValueError:
            source_name = Path(source_name).stem

        self._writer = EdgeDetectionWriter(
            output_dir=self.config.output_dir,
            source_name=source_name,
            flush_interval=self.config.csv_flush_interval,
        )

    def _should_record_clip(self, elapsed: float) -> bool:
        """Check if it's time to start a new validation clip."""
        if self.config.validation_clip_interval_s <= 0:
            return False
        if self._clip_writer is not None:
            return False  # Already recording a clip
        return (
            (elapsed - self._last_clip_time) >= 
            self.config.validation_clip_interval_s
        )
    
    def _start_validation_clip(self, frame:np.ndarray) -> None:
        """
        Begin recording a validation clip.

        The clip is written at the effective frame rate (accounting for
        frame_skip) so that playback speed matches real time.
        """
        if self._capture is None:
            logger.warning("Cannot start validation clip: capture not open")
            return
        
        clips_dir = Path(self.config.output_dir) / "validation_clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clip_path = clips_dir / f"validation_{timestamp}.mp4"

        # Use the effective fps (after frame_skip) so the clip plays
        # back at the correct speed. If the source is 25fps and
        # frame_skip=5, we're only seeing 5 frames per second, so the
        # clip should be written at 5fps.
        native_fps = self._capture.fps if self._capture.fps > 0 else 25.0
        effective_fps = native_fps / max(self.config.frame_skip, 1)
        h, w = frame.shape[:2]

        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        self._clip_writer = cv2.VideoWriter(
            str(clip_path), fourcc, effective_fps, (w, h)
        )
        self._clip_frame_count = 0
        self._clip_effective_fps = effective_fps

        logger.info(
            "Recording validation clip: %s (%.1f fps effective)",
            clip_path, effective_fps,
        )

    def _write_clip_frame(self, frame: np.ndarray) -> None:
        """Write a frame to the current validation clip."""
        if self._clip_writer is None:
            return
        
        self._clip_writer.write(frame)
        self._clip_frame_count += 1

        # Use effective fps for duration calculation so the clip actually lasts
        # validation_clip_duration_s in real timme.
        max_frames = int(
            self.config.validation_clip_duration_s * self._clip_effective_fps
        )

        if self._clip_frame_count >= max_frames:
            self._clip_writer.release()
            self._clip_writer = None
            self._last_clip_time = time.monotonic() - self._start_time
            logger.info(
                "Validation clip complete (%d frames, %.0fs)",
                self._clip_frame_count,
                self.config.validation_clip_duration_s,
            )

    def run(self) -> None:
        """
        Main inference loop.

        Runs until the source is exhausted (video file) or interrupted
        (camera / Ctrl+C). Handles cleanup on exit.
        """     
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        # Initialise _start_time BEFORE any setup that might raise, so
        # the finally block can always compute elapsed time safely.
        self._start_time = time.monotonic()
        processed = 0
        total_inference_ms = 0.0

        self._validate_artifact()
        self._load_model()
        self._open_capture()
        self._open_writer()

        logger.info(
            "Starting inference (imgsz=%d, conf=%.2f, frame_skip=%d)",
            self.config.imgsz, self.config.conf_threshold,
            self.config.frame_skip,
        )

        if (self._capture is None 
                or self._session is None 
                or self._writer is None):
            logger.error("Runtime not properly initialised. Exiting.")
            return

        try:
            for frame, frame_number in self._capture.iter_frames(
                frame_skip=self.config.frame_skip,
            ):
                elapsed = time.monotonic() - self._start_time

                # Preprocess
                blob, ratio, pad = preprocess(frame, self.config.imgsz)

                # Inference
                t0 = time.perf_counter()
                raw_output = self._session.run(None, {self._input_name: blob})
                t1 = time.perf_counter()
                inference_ms = (t1 - t0) * 1000
                total_inference_ms += inference_ms

                # Narrow type from ONNX union to list[np.ndarray]
                output = [
                    arr for arr in raw_output
                    if isinstance(arr, np.ndarray)
                ]
                if len(output) != len(raw_output):
                    raise TypeError("ONNX model returned non-ndarray output(s)")

                # Postprocess
                detections = postprocess(
                    output,
                    conf_threshold=self.config.conf_threshold,
                    iou_threshold=self.config.iou_threshold,
                )

                # Scale boxes back to original frame coordinates
                detections = scale_boxes_to_original(detections, ratio, pad)

                # Write detections
                timestamp = frame_number / self._capture.fps if self._capture.fps > 0 else 0.0
                if detections:
                    self._writer.write(
                        detections, frame_number, timestamp,
                        class_names=self.config.class_names,
                    )

                # Validation clip
                if self._should_record_clip(elapsed):
                    self._start_validation_clip(frame)
                if self._clip_writer is not None:
                    self._write_clip_frame(frame)

                processed += 1

                # Periodic log
                if processed % 500 == 0:
                    avg_ms = total_inference_ms / processed
                    logger.info(
                        "Processed %d frames | avg inference: %.1f ms | "
                        "elapsed: %.0f s",
                        processed, avg_ms, elapsed,
                    )
        
        except KeyboardInterrupt:
            logger.info("Inference interrupted by user")

        finally:
            # Cleanup
            if self._clip_writer is not None:
                self._clip_writer.release()
            if self._writer is not None:
                self._writer.close()
            if self._capture is not None:
                self._capture.release()

            elapsed = time.monotonic() - self._start_time
            avg_ms = total_inference_ms / max(processed, 1)
            logger.info(
                "Runtime finished: %d frames in %.1f s (avg %.1f ms/frame, "
                "%.1f effective FPS)",
                processed, elapsed, avg_ms,
                processed / max(elapsed, 0.001),
            )