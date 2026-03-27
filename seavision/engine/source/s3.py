"""Loading video files from AWS S3 as a video source."""

import logging
import re
from typing import Iterator, Optional, Tuple

import cv2
import numpy as np

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from .base import FrameContext, VideoMetadata, VideoSource

logger = logging.getLogger(__name__)


def parse_s3_uri(uri: str) -> Tuple[str, str]:
    """
    Parse an S3 URI into bucket and key components.

    Args:
        uri: S3 URI (e.g., "s3://bucket-name/path/to/.file.ts").

    Returns:
        Tuple of (bucket_name, key).
    
    Raises:
        ValueError: If the URI is not a valid S3 URI.
    """

    match = re.match(r"^s3://([^/]+)/(.+)$", uri)
    if not match:
        raise ValueError(
            f"Invalid S3 URI: {uri}. Expected format: s3://bucket/key"
        )
    return match.group(1), match.group(2)


class S3VideoSource(VideoSource):
    """
    Loads video frames from an AWS S3 bucket using pre-signed URLs.
    
    Uses OpenCV's HTTP streaming capability to read video directly from S3
    without downloading to a temporary file.
    
    Attributes:
        uri: S3 URI to the video file (e.g., "s3://bucket-name/path/to/.file.ts").
    
    Example:
        with S3VideoSource("s3://my-bucket/footage/clip_001.ts") as source:
            metadata = source.get_metadata()
            print(f"Processing {metadata.duration:.1f}s video")
            
            for frame, context in source.iter_frames():
                # process frame
                pass
    
    Note:
        Requires boto3 to be installed and AWS credentials configured.
        Credentials are read from environment variables, ~/.aws/credentials,
        IAM role (if running on AWS infrastructure), or SSO profile.
    """

    def __init__(
        self,
        uri: str,
        presigned_url_expiry: int = 14400,
        region_name: Optional[str] = None,
        profile_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ):
        """
        Initialise the S3 video source.

        Args:
            uri: S3 URI to the video file (e.g., "s3://bucket/path/video.ts").
            presigned_url_expiry: Expiry time in seconds for the presigned URL.
                Default is 14400 (4 hours).
            region_name: AWS region name. If None, uses default region from 
                config.
            profile_name: AWS profile name for SSO authentication. If None,
                uses default credentials chain.
            endpoint_url: Custom S3-compatible endpoint URL (e.g. Wasabi).
        
        Raises:
            ImportError: If boto3 is not installed.
            ValueError: If the URI is invalid.
        """
        
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for S3 support. "
                "Install with `pip install boto3`."
            )
        
        self.uri = uri
        self.presigned_url_expiry = presigned_url_expiry
        self.bucket, self.key = parse_s3_uri(uri)

        # Create S3 client via session (supports SSO profiles and custom endpoints)
        session = boto3.Session(
            profile_name=profile_name,
            region_name=region_name,
        )
        self._s3_client = session.client("s3", endpoint_url=endpoint_url)

        # State - lazy initialisation
        self._presigned_url: Optional[str] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._metadata: Optional[VideoMetadata] = None

    
    def _ensure_connected(self) -> None:
        """
        Ensure the video capture is connected and ready.

        Generates pre-signed URL and open VideoCapture on first call.

        Raises:
            RuntimeError: If unable to open video stream.
        """

        if self._cap is not None:
            return  # Already connected

        # Generate pre-signed URL
        try:
            self._presigned_url = self._s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": self.key},
                ExpiresIn=self.presigned_url_expiry,
            )
            logger.debug(f"Generated pre-signed URL for {self.uri}")
        except ClientError as e:
            raise RuntimeError(
                f"Failed to generate pre-signed URL for {self.uri}: {e}"
            )
        
        # Open video capture
        self._cap = cv2.VideoCapture(self._presigned_url)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open video stream from S3: {self.uri}. "
                "OpenCV may not support streaming this format via HTTP."
            )

        # Validate we can read metadata
        frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            logger.warning(
                f"Frame count not available for {self.uri}. "
                "Progress tracking may be inaccurate."
            )


    def get_metadata(self) -> VideoMetadata:
        """
        Get metadata about the video file.

        Returns:
            VideoMetadata object with file properties.
        """       
        self._ensure_connected()
        
        if self._metadata is not None:
            return self._metadata
        
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0.0

        self._metadata = VideoMetadata(
            source_file=self.uri,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            duration=duration,
        )
        
        return self._metadata


    def iter_frames(self) -> Iterator[Tuple[np.ndarray, FrameContext]]:
        """
        Iterate over frames in the video file.

        Yields:
            Tuple of (frame, context) where frame is a BGR numpy array
            and context contains metadata about the frame.
        """
        self._ensure_connected()

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        frame_number = 0

        while True:
            ret, frame = self._cap.read()
            
            if not ret:
                break  # End of video

            timestamp = frame_number / fps if fps > 0 else 0.0

            context = FrameContext(
                source_file=self.uri,
                frame_number=frame_number,
                timestamp=timestamp,
                fps=fps,
            )

            yield frame, context
            frame_number += 1


    
    def close(self) -> None:
        """Release the video capture resource."""
        if self._cap is not None and self._cap.isOpened():
            self._cap.release()
            self._cap = None
        self._presigned_url = None
        self._metadata = None
