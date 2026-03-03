"""Video source discovery functions."""

import logging
from pathlib import Path
from typing import List, Optional

from .base import VideoSource
from .local import LocalVideoSource

logger = logging.getLogger(__name__)


def discover_local_videos(
        path: str,
        pattern: str = "*.ts"
) -> List[VideoSource]:
    """
    Discover video files on the local file system.

    Args:
        path: Path to a video file or directory containing videos.
        pattern: Glob pattern to match video files in directories.
    
    Returns:
        List of LocalVideoSource instances (unopened - will opened when iterated
        in the pipeline).
    
    Raises:
        FileNotFoundError: If the specified path does not exist.
        ValueError: If no video files are found in the specified directory.
    
    Example:
        sources = discover_local_videos("./footage/", "*.ts")
        for source in sources:
            with source:
                for frame, context in source.iter_frames():
                    # process frame        
    """

    input_path = Path(path)

    if input_path.is_file():
        logger.debug(f"Discovered single video: {input_path}")
        return [LocalVideoSource(str(input_path))]

    elif input_path.is_dir():
        video_paths = list(input_path.glob(pattern))
        
        if not video_paths:
            raise ValueError(
                f"No files matching '{pattern}' found in {input_path}"
            )
        
        logger.debug(f"Discovered {len(video_paths)} videos in: {input_path}")
        return [LocalVideoSource(str(p)) for p in video_paths]
    
    else:
        raise FileNotFoundError(f"Path not found: {input_path}")

def discover_s3_videos(
    bucket: str,
    prefix: str = "",
    pattern: str = "*.ts",
    region_name: Optional[str] = None,
    profile_name: Optional[str] = None,
    endpoint_url: Optional[str] = None,
) -> List[VideoSource]:
    """
    Discover video files in an S3 bucket.
    
    Args:
        bucket: S3 bucket name.
        prefix: Key prefix to filter objects (e.g., "footage/2025/").
        pattern: Glob pattern for matching video filenames (e.g. "*.ts").
        region_name: AWS region name, if None uses the default from config.
        profile_name: AWS profile name for SSO authentication. If None,
            uses default credentials chain.
        endpoint_url: Custom S3-compatible endpoint URL (e.g. Wasabi).
    
    Returns:
        List of S3VideoSource instances (not yet connected).
    
    Raises:
        ImportError: If boto3 is not installed.
        ValueError: If no matching video files are found.
    
    Example:
        # Using SSO profile
        sources = discover_s3_videos(
            bucket="my-buoy-footage",
            prefix="2025/10/",
            pattern="*.ts",
            profile_name="sso-profile-name"
        )
        for source in sources:
            with source:
                for frame, context in source.iter_frames():
                    # process frame
                    pass
    """
    try:
        import boto3
    except ImportError:
        raise ImportError(
            "boto3 is required for S3 support. "
            "Install with `pip install boto3`."
        )

    from fnmatch import fnmatch
    from .s3 import S3VideoSource

    # Create S3 client via session (supports SSO profiles and custom endpoints)
    session = boto3.Session(
        profile_name=profile_name,
        region_name=region_name,
    )
    s3_client = session.client("s3", endpoint_url=endpoint_url)
    paginator = s3_client.get_paginator("list_objects_v2")

    matching_keys = []

    # Paginate through all objects in the bucket with the given prefix
    page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

    for page in page_iterator:
        if "Contents" not in page:
            continue

        for obj in page["Contents"]:
            key = obj["Key"]
            filename = key.split("/")[-1]
            
            if fnmatch(filename, pattern):
                matching_keys.append(key)

    if not matching_keys:
        raise ValueError(
            f"No files matching '{pattern}' found in s3://{bucket}/{prefix}"
        )
    
    # Sort for deterministic order
    matching_keys.sort()

    logger.debug(f"Discovered {len(matching_keys)} videos in s3://{bucket}/{prefix}")

    return [
        S3VideoSource(
            f"s3://{bucket}/{key}",
            region_name=region_name,
            profile_name=profile_name,
            endpoint_url=endpoint_url,
        )
        for key in matching_keys
    ]
