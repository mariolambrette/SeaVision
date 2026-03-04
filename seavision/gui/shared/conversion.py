"""Conversion utilities between OpenCV/numpy and Qt image types."""

import numpy as np
from PySide6.QtGui import QImage

def numpy_bgr_to_qimage(frame: np.ndarray) -> QImage:
    """
    Convert a BGR or BGRA numpy array to a QImage.

    Args:
        frame: numpy array of shape (H, W, 3) for BGR or (H, W, 4) for BGRA.
            Must be dtype uint8 and contiguous.

    Returns:
        A QImage that owns its own pixel data (safe to use after the numpy array
            is freed).

    Raises:
        ValueError: If the input array does not have 3 or 4 channels.
    """

    # Check the shape of the input array - images are 3D arrays
    if frame.ndim != 3:
        raise ValueError(
            f"Expected 3D array (H, W, C), got shape {frame.shape}"
        )
    
    height, width, channels = frame.shape

    # Define the correct QImage formatter based on the number of channels
    if channels == 3:
        fmt = QImage.Format.Format_BGR888
    elif channels == 4:
        fmt = QImage.Format.Format_BGRA8888
    else:
        raise ValueError(
            f"Expected 3 (BGR) or 4 (BGRA) channels, got {channels}"
        )
    
    # Make the array contiguous in memory (C order) to ensure QImage can use it 
    # directly
    frame = np.ascontiguousarray(frame)
    bytes_per_line = channels * width

    # Create the QImage
    image = QImage(frame.data, width, height, bytes_per_line, fmt)

    # Use image.copy() to ensure the QImage owns its own data, so it remains 
    # valid even if the original numpy array is freed

    # TODO: This approach is performance intensive see note in Phase 1 guide.
    # A more fficient approach may need to be implemented here.
    return image.copy()
