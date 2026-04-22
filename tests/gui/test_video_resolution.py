"""Tests for video path resolution logic."""

from pathlib import Path

from seavision.gui.shared.session_utils import resolve_video_paths


class TestResolveVideoPaths:
    """Test the video path resolution logic."""

    def test_resolves_matching_filename(self, tmp_path):
        """A video file in the directory should be resolved by filename."""
        # Create a fake video file
        video_file = tmp_path / "video1.ts"
        video_file.touch()

        resolved, s3 = resolve_video_paths(
            ["footage/video1.ts"],
            str(tmp_path)
        )

        assert "footage/video1.ts" in resolved
        assert resolved["footage/video1.ts"] == str(video_file)
        assert s3 == []

    def test_ignores_path_prefix(self, tmp_path):
        """Only the filename matters, not the directory in the CSV."""
        video_file = tmp_path / "clip.ts"
        video_file.touch()

        resolved, _ = resolve_video_paths(
            ["some/deep/path/clip.ts"],
            str(tmp_path),
        )

        assert "some/deep/path/clip.ts" in resolved

    def test_missing_file_not_resolved(self, tmp_path):
        """A source with no matching file should not appear in results."""
        resolved, _ = resolve_video_paths(
            ["missing_video.ts"],
            str(tmp_path),
        )

        assert len(resolved) == 0

    def test_s3_sources_separated(self, tmp_path):
        """S3 URIs should be collected separately."""
        video_file = tmp_path / "local.ts"
        video_file.touch()

        resolved, s3 = resolve_video_paths(
            ["local.ts", "s3://bucket/remote.ts"],
            str(tmp_path),
        )

        assert "local.ts" in resolved
        assert "s3://bucket/remote.ts" in s3

    def test_multiple_videos(self, tmp_path):
        """Multiple matching videos should all resolve."""
        for name in ["clip_001.ts", "clip_002.ts", "clip_003.ts"]:
            (tmp_path / name).touch()

        resolved, _ = resolve_video_paths(
            ["clip_001.ts", "clip_002.ts", "clip_003.ts"],
            str(tmp_path),
        )

        assert len(resolved) == 3

    def test_empty_sources(self, tmp_path):
        """An empty source list should return empty results."""
        resolved, s3 = resolve_video_paths([], str(tmp_path))

        assert resolved == {}
        assert s3 == []