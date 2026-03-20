"""
Local file cache for remote-sourced videos (e.g. from S3)

Downloads videos from the remote source to a local cache directory so that
SeekableVideoSource can open them with random access seeking. The cache
persists between sessions.

Supported sources:
- S3 (e.g. s3://my-bucket/path/to/video.mp4)

This module currently depends on boto3 but has no Qt dependency.
"""

import hashlib
import logging
import shutil
from pathlib import Path

from seavision.engine.source.s3 import parse_s3_uri

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


_DEFAULT_CACHE_DIR = Path.home() / ".seavision" / "cache"


class S3VideoCache:
    """
    Local file cache for S3 videos.

    Downloads videos from S3 on demand and stored them in a flat directory keyed
    by a hash of the S3 URI.
    """

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or _DEFAULT_CACHE_DIR

    def _ensure_cache_dir(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _cache_key(s3_uri: str) -> str:
        """
        Derive a filesystem-safe cache ky from an S3 URI.

        Uses SHA-256 truncated to 16 hex chars plus the original filename for
        readability.
        """
        uri_hash = hashlib.sha256(s3_uri.encode()).hexdigest()[:16]
        filename = Path(s3_uri.split("/")[-1]).name
        return f"{uri_hash}_{filename}"
    

    def get_or_download(
        self,
        s3_uri: str,
        profile_name: str | None = None
    ) -> Path:
        """
        Return the local path for an S3 video, downloading if needed.

        Downloads to a .downloading temp file first, then renames automatically
        to prevent partial files being treated as complete.
        """
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for S3 video downloads. "
                "Install with pip install boto3"
            )
        
        self._ensure_cache_dir()
        cache_key = self._cache_key(s3_uri)
        local_path = self.cache_dir / cache_key

        if local_path.exists():
            logger.debug("Cache hit for %s", s3_uri)
            return local_path
        
        logger.info("Downloading %s to cache...", s3_uri)
        bucket, key = parse_s3_uri(s3_uri)
        tmp_path = local_path.with_suffix(".downloading")

        try:
            session = boto3.Session(profile_name=profile_name)
            s3_client = session.client("s3")

            s3_client.download_file(bucket, key, str(tmp_path))
            tmp_path.rename(local_path)
            logger.info("Cached %s to %s", s3_uri, local_path)
            return local_path
        
        except NoCredentialsError:
            if tmp_path.exists():
                tmp_path.unlink()
            raise RuntimeError(
                "AWS credentials not found. "
                "Run 'aws sso login' before opening S3 sessions."
            )
        
        except ClientError as e:
            if tmp_path.exists():
                tmp_path.unlink()
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ExpiredToken":
                raise RuntimeError(
                    "AWS credentials have expired. "
                    "Run 'aws sso login' to refresh them."
                )
            raise RuntimeError(
                f"Failed to download {s3_uri}:\n\n{e}"
            ) from e
        
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            raise RuntimeError(
                f"Failed to download {s3_uri}:\n\n{e}"
            ) from e
        
    
    def calculate_download_size(
        self,
        s3_uris: list[str],
        profile_name: str | None = None,
    ) -> tuple[int, list[str]]:
        """
        Calculate total download size for uncached S3 URIs using HEAD requests.

        Returns:
            Tuple of (total_bytes, uris_needing_downloading)
        """
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for S3 video downloads. "
                "Install with pip install boto3"
            )
        
        session = boto3.Session(profile_name=profile_name)
        s3_client = session.client("s3")

        total_bytes = 0
        need_download: list[str] = []

        for uri in s3_uris:
            if (self.cache_dir / self._cache_key(uri)).exists():
                continue

            bucket, key = parse_s3_uri(uri)
            try:
                response = s3_client.head_object(
                    Bucket=bucket,
                    Key=key
                )
                total_bytes += response["ContentLength"]
                need_download.append(uri)
            
            except (ClientError, NoCredentialsError) as e:
                raise RuntimeError(
                    f"Cannot determine size of {uri}: {e}"
                ) from e

            except Exception as e:
                # Catches connection errors, DNS failures, timeouts,
                # and any other network-level issue from boto3/urllib3
                raise RuntimeError(
                    f"Cannot connect to S3 for {uri}:\n\n{e}"
                ) from e
            
        return total_bytes, need_download
    

    def cache_size(self) -> int:
        """Return total size of cached files in bytes."""
        if not self.cache_dir.exists():
            return 0
        return sum(
            f.stat().st_size
            for f in self.cache_dir.iterdir()
            if f.is_file() and not f.name.endswith(".downloading")
        )
    
    def clear_cache(self) -> int:
        """Delete all cached files. Returns bytes freed."""
        freed = self.cache_size()
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            logger.info(
                "Cleared cache: %.1f MB freed", freed / (1024**2)
            )
        return freed
    
    def is_cached(self, s3_uri: str) -> bool:
        """Check whether a specific URI is already cached."""
        return (self.cache_dir / self._cache_key(s3_uri)).exists()
