"""Tests for the S3 video cache with mocked BOTO3."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from seavision.gui.validation.video_cache import S3VideoCache


class TestCacheKeyDerivation:

    def test_same_uri_same_key(self):
        cache = S3VideoCache()
        key1 = cache._cache_key("s3://bucket/path/video.ts")
        key2 = cache._cache_key("s3://bucket/path/video.ts")
        assert key1 == key2

    def test_different_uri_different_key(self):
        cache = S3VideoCache()
        key1 = cache._cache_key("s3://bucket-a/video.ts")
        key2 = cache._cache_key("s3://bucket-b/video.ts")
        assert key1 != key2

    def test_key_includes_filename(self):
        cache = S3VideoCache()
        key = cache._cache_key("s3://bucket/path/clip_001.ts")
        assert "clip_001.ts" in key


class TestCacheHitMiss:

    def test_cache_hit_returns_immediately(self, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        uri = "s3://bucket/video.ts"
        cached_file = tmp_path / cache._cache_key(uri)
        cached_file.write_bytes(b"fake video data")

        result = cache.get_or_download(uri)
        assert result == cached_file

    @patch("seavision.gui.validation.video_cache.boto3")
    def test_cache_miss_downloads(self, mock_boto3, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        uri = "s3://bucket/video.ts"

        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client
        mock_boto3.Session.return_value = mock_session

        def fake_download(bucket, key, path, Callback=None):
            Path(path).write_bytes(b"downloaded data")

        mock_client.download_file.side_effect = fake_download

        result = cache.get_or_download(uri)
        assert result.exists()
        mock_client.download_file.assert_called_once()


class TestCalculateDownloadSize:

    @patch("seavision.gui.validation.video_cache.boto3")
    def test_aggregates_sizes(self, mock_boto3, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client
        mock_boto3.Session.return_value = mock_session
        mock_client.head_object.side_effect = [
            {"ContentLength": 1000},
            {"ContentLength": 2000},
        ]

        total, need = cache.calculate_download_size([
            "s3://bucket/a.ts", "s3://bucket/b.ts",
        ])
        assert total == 3000
        assert len(need) == 2

    @patch("seavision.gui.validation.video_cache.boto3")
    def test_excludes_cached(self, mock_boto3, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        uri_a = "s3://bucket/a.ts"
        (tmp_path / cache._cache_key(uri_a)).write_bytes(b"cached")

        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client
        mock_boto3.Session.return_value = mock_session
        mock_client.head_object.return_value = {"ContentLength": 5000}

        total, need = cache.calculate_download_size([
            uri_a, "s3://bucket/b.ts",
        ])
        assert total == 5000
        assert len(need) == 1


class TestCacheManagement:

    def test_cache_size(self, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        (tmp_path / "file_a").write_bytes(b"x" * 100)
        (tmp_path / "file_b").write_bytes(b"y" * 200)
        assert cache.cache_size() == 300

    def test_excludes_downloading(self, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        (tmp_path / "complete.ts").write_bytes(b"x" * 100)
        (tmp_path / "partial.downloading").write_bytes(b"y" * 500)
        assert cache.cache_size() == 100

    def test_clear_cache(self, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        (tmp_path / "file_a").write_bytes(b"x" * 100)
        freed = cache.clear_cache()
        assert freed == 100
        assert not tmp_path.exists()

    def test_is_cached(self, tmp_path):
        cache = S3VideoCache(cache_dir=tmp_path)
        uri = "s3://bucket/video.ts"
        assert not cache.is_cached(uri)
        (tmp_path / cache._cache_key(uri)).write_bytes(b"data")
        assert cache.is_cached(uri)
