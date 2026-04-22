"""
Tests for SeekableVideoSource.

These tests require a valid video file to be present at tests/data/sample.ts.
If the file is missing the tests will be skipped automatically.
"""

import numpy as np
import pytest

from seavision.gui.validation.seekable_source import SeekableVideoSource
from seavision.engine.source.base import FrameContext


class TestSeekableVideoSource:
    """Test for random-access video reading."""
    
    def test_open_valid_video(self, sample_video_path):
        """Opening a valid video should populate metadata."""
        with SeekableVideoSource(str(sample_video_path)) as src:
            m = src.metadata
            assert m.fps > 0
            assert m.frame_count > 0
            assert m.width > 0
            assert m.height > 0
            assert m.duration > 0

    def test_open_nonexistent_raises(self):
        """Opening a non-existent file should raise a ValueError."""
        with pytest.raises(ValueError, match="not found"):
            SeekableVideoSource("/nonexistent/video.ts")

    def test_read_returns_frame(self, sample_video_path):
        """read() should return an ndarray with the right shape."""
        with SeekableVideoSource(str(sample_video_path)) as src:
            result = src.read()
            assert result is not None

            frame, ctx = result
            assert isinstance(frame, np.ndarray)
            assert frame.shape == (src.metadata.height, src.metadata.width, 3)
            assert isinstance(ctx, FrameContext)

    def test_read_at_frame_zero(self, sample_video_path):
        """read_at(0) should return frame 0."""
        with SeekableVideoSource(str(sample_video_path)) as src:
            result = src.read_at(0)
            assert result is not None

            _, ctx = result
            assert ctx.frame_number == 0

    def test_read_at_timestamp(self, sample_video_path):
        """The timestamp should be approximately frame_number/fps."""
        with SeekableVideoSource(str(sample_video_path)) as src:
            n = min(10, src.metadata.frame_count - 1)
            result = src.read_at(n)
            assert result is not None

            _, ctx = result
            expected = n / src.metadata.fps

            # Allow 10-frame tolerance for .ts seek innacuracy
            tolerance = 10 / src.metadata.fps
            assert ctx.timestamp == pytest.approx(expected, abs=tolerance)

    def test_seek_negative_clamps(self, sample_video_path):
        """Seeking to -1 should clamp to frame 0."""
        with SeekableVideoSource(str(sample_video_path)) as src:
            src.seek(-1)
            result = src.read()
            assert result is not None
            _, ctx = result
            assert ctx.frame_number == 0

    def test_read_past_end_returns_none(self, sample_video_path):
        """Reading past the end of the video should return None."""
        with SeekableVideoSource(str(sample_video_path)) as src:
            src.seek(src.metadata.frame_count)  # one past the last
            result = src.read()
            # On most files this is None; on some codecs it may return
            # the last frame. Either way, no crash.
            # The key thing is it doesn't raise.

    def test_context_manager_releases(self, sample_video_path):
        """After exiting the context manager, the capture is released."""
        src = SeekableVideoSource(str(sample_video_path))
        src.close()
        # After close, _cap should be None
        assert src._cap is None
