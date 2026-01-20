"""Frame stabilisation using feature-based homography."""

from dataclasses import dataclass
from typing import Optional, Tuple
import cv2
import numpy as np


@dataclass
class StabiliserConfig:
    """
    Configuration for frame stabilisation.

    # TODO: Glossary document which defines these things?
    Attributes:
        feature_detector: Feature detector type (e.g. 'ORB', 'AKAZE').
        max_features: Maximum number of features to detect.
        match_ratio: Lowe's ratio test threshold for feature matching.
        min_matches: Minimum number of matches to compute homography.
        ransac_threshold: RANSAC reprojection threshold for homography.
    """

    feature_detector: str = "ORB"
    max_features: int = 500
    match_ratio: float = 0.75
    min_matches: int = 10
    ransac_threshold: float = 5.0


class FrameStabiliser:
    """
    Stabilises frames by aligning to the previous frame.

    Uses feature-based homography estimation to compensate for camera motion.

    Example:
        stabiliser = FrameStabiliser()
        
        for frame in video_frames:
            stable_frame = stabiliser.stabilise(frame)
            # process stable_frame
    """

    def __init__(self, config: Optional[StabiliserConfig] = None):
        """
        Initialise the frame stabiliser.

        Args:
            config: Configuration for the stabiliser. If None, defaults are used.
        """

        self.config = config or StabiliserConfig()

        # Initialise the feature detector
        # TODO: Are thee anymore obvous detector options that shoul dbe implemented?
        if self.config.feature_detector == "ORB":
            self._detector = cv2.ORB_create(nfeatures=self.config.max_features)
        elif self.config.feature_detector == "AKAZE":
            self._detector = cv2.AKAZE_create()
        else:
            raise ValueError(f"Unknown detector: {self.config.feature_detector}")
        
        # Brute-force matcher with Hamming distance (for binary descriptors)
        # TODO: What is a matcher? this should be in the glossary
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

        # State
        self._prev_grey: Optional[np.ndarray] = None
        self._prev_keypoints: Optional[list] = None
        self._prev_descriptors: Optional[np.ndarray] = None

    def stabilise(self, frame: np.ndarray) -> Tuple[np.ndarray, bool]:
        """
        Stabilise a frame by aligning it to the previous frame.

        Args:
            frame: Input BGR frame as a numpy array.

        Returns:
            Tuple of (stabilised_frame, is_stabilised) where stabilised_frame
            is the aligned frame and is_stabilised indicates if alignment was 
            applied. Returns the original frame if is_stabilised is False.
        """

        # Convert to greyscale - feature detection works on intensity values
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect distinctive visual features (corners, edges) and compute
        # binary descriptors that summarise the local appearance around each
        keypoints, descriptors = self._detector.detectAndCompute(grey, None)

        # First frame - nothing to align to
        if self._prev_grey is None:
            self._update_reference(grey, keypoints, descriptors)
            return frame, True
        
        # Not enough features in current frame
        if descriptors is None or len(keypoints) < self.config.min_matches:
            self._update_reference(grey, keypoints, descriptors)
            return frame, False
        
        # Match features to previous frame. For each feature in the previous
        # frame, find the 2 most similar features in the current frame (k=2).
        # Similarity is measured by Hamming distance between binary descriptors.
        matches = self._matcher.knnMatch(
            self._prev_descriptors, descriptors, k=2
        )

        # Apply Lowe's ratio test to filter ambiguous matches. A match is
        # considered good if the best match (m) is significantly better than
        # the second-best match (n). This rejects features that could match
        # multiple locations (e.g., repetitive patterns).
        good_matches = []
        for m, n in matches:
            if m.distance < self.config.match_ratio * n.distance:
                good_matches.append(m)
        
        # Not enough good matches
        if len(good_matches) < self.config.min_matches:
            self._update_reference(grey, keypoints, descriptors)
            return frame, False
        
        # Extract matched point coordinates:
        # - src_pts: where features were located in the PREVIOUS frame
        # - dst_pts: where those same features are in the CURRENT frame
        # The difference between these tells us how the camera moved.
        src_pts = np.float32([
            self._prev_keypoints[m.queryIdx].pt for m in good_matches
        ]).reshape(-1, 1, 2)
        dst_pts = np.float32([
            keypoints[m.trainIdx].pt for m in good_matches
        ]).reshape(-1, 1, 2)

        # Compute homography matrix H that maps dst_pts -> src_pts.
        # H is a 3x3 transformation matrix that describes the camera motion
        # (rotation, translation, perspective change) between frames.
        # RANSAC robustly estimates H by ignoring outlier matches (e.g., from
        # moving objects or mismatches).
        H, mask = cv2.findHomography(
            dst_pts, src_pts, 
            cv2.RANSAC, 
            self.config.ransac_threshold
        )

        if H is None:
            self._update_reference(grey, keypoints, descriptors)
            return frame, False
        
        # Warp current frame to align with previous frame.
        # This applies the inverse camera motion, so stationary background
        # objects appear in the same position as the previous frame.
        height, width = frame.shape[:2]
        stabilised_frame = cv2.warpPerspective(frame, H, (width, height))

        # Update reference frame
        self._update_reference(grey, keypoints, descriptors)
        return stabilised_frame, True
    
    def _update_reference(
        self, 
        grey: np.ndarray, 
        keypoints: Tuple, 
        descriptors: Optional[np.ndarray]
    ) -> None:
        """Update the reference frame and features."""
        self._prev_grey = grey
        self._prev_keypoints = keypoints
        self._prev_descriptors = descriptors

    def reset(self) -> None:
        """Reset the stabiliser state."""
        self._prev_grey = None
        self._prev_keypoints = None
        self._prev_descriptors = None
