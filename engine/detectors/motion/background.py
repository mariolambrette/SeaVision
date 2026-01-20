"""Background subtraction for foreground detection."""

from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np


@dataclass
class BackgroundConfig:
    """
    Configuration for background subtraction.
    
    Attributes:
        history: Number of frames used to build the background model.
        var_threshold:Variance threshold for foreground classification.
        detect_shadows: Whether to detect shadows in the foreground mask.
        learning_rate: Background model learning rate. Use -1 for auto,
            or a value in [0,1] where higher = faster adaptation.
    """

    history: int = 600 # 1 minute at 10 FPS
    var_threshold: float = 16.0
    detect_shadows: bool = True
    learning_rate: float = -1.0  # Auto


class BackgroundModel:
    """
    Adaptive background subtraction using MOG2.

    Maintains a per-pixel Gaussian mixture model (GMM) to distinguish forground
    (moving objects) from background (static scene).

    Example:
        bg_model = BackgroundModel()
        
        for frame in stabilised_frames:
            fg_mask = bg_model.apply(frame)
            # mask is binary image where 255 = foreground; 0 = background
    """

    def __init__(self, config: Optional[BackgroundConfig] = None):
        """
        Initialise the background model.

        Args:
            config: Configuration for the background model. If None, defaults
                are used.
        """

        self.config = config or BackgroundConfig()

        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=self.config.history,
            varThreshold=self.config.var_threshold,
            detectShadows=self.config.detect_shadows,
        )
    
    def apply(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply background subtraction to a frame.

        Args:
            frame: Input BGR frame as a numpy array - should already be 
                stabilised.

        Returns:
            Foreground mask as a binary numpy array (uint8) where:
            255 = foreground; 0 = background.
        """

        mask = self._subtractor.apply(
            frame,
            learningRate=self.config.learning_rate
        )

        # Ensure binary output (MOG2 can produce grey values for shadows)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

        return mask
    
    def reset(self) -> None:
        """
        Reset the background model to initial state.
        """

        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=self.config.history,
            varThreshold=self.config.var_threshold,
            detectShadows=self.config.detect_shadows,
        )