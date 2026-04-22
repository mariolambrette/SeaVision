"""Tests for the edge frame capture module."""

import numpy as np
import pytest
import cv2
from pathlib import Path

from seavision.edge.capture import FrameCapture, CaptureError


class TestFrameCapture:
    """Test frame capture from video files."""

    @pytest.fixture
    def test_video(self, tmp_path):
        """Create a minimal test video file."""
        video_path = tmp_path / "test.mp4"
        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(video_path), fourcc, 10.0, (64, 48))
        for i in range(20):
            frame = np.full((48, 64, 3), i * 10, dtype=np.uint8)
            writer.write(frame)
        writer.release()
        return str(video_path)

    def test_opens_video_file(self, test_video):
        with FrameCapture(test_video) as cap:
            assert cap.width == 64
            assert cap.height == 48
            assert cap.fps == pytest.approx(10.0, abs=1.0)

    def test_iter_frames_yields_all(self, test_video):
        with FrameCapture(test_video) as cap:
            frames = list(cap.iter_frames())
            assert len(frames) == 20
            frame, num = frames[0]
            assert frame.shape == (48, 64, 3)
            assert num == 0

    def test_frame_skip(self, test_video):
        with FrameCapture(test_video) as cap:
            frames = list(cap.iter_frames(frame_skip=5))
            # Frames 0, 5, 10, 15 = 4 frames
            assert len(frames) == 4
            assert frames[0][1] == 0
            assert frames[1][1] == 5

    def test_invalid_source_raises(self):
        with pytest.raises(CaptureError):
            FrameCapture("/nonexistent/video.mp4")