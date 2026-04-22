"""Tests for the BGR-to-QImage conversion helper."""

import numpy as np

class TestNumpyBGRToQImage:
    """Test the numpy_bgr_to_qimage conversion function."""

    def test_basic_3_channel(self, qapp):
        """
        A 480x640 BGR array should produce a valid QImage of the same size.
        """
        from seavision.gui.shared.conversion import numpy_bgr_to_qimage
        from PySide6.QtGui import QImage

        # Create a dummy frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Convert to QImage
        image = numpy_bgr_to_qimage(frame)

        # Check the type and size of the resulting QImage
        assert isinstance(image, QImage)
        assert image.width() == 640
        assert image.height() == 480

    def test_pixel_colour_bgr(self, qapp):
        """
        A BGR pixel of (255, 0, 0) is pure blue. The QImage should report
        that pixel as blue.
        """
        from seavision.gui.shared.conversion import numpy_bgr_to_qimage

        # Create a dummy 1x1x3 array
        frame = np.zeros((1, 1, 3), dtype=np.uint8)

        # Convert pixel colour ot blue
        frame[0,0] = [255, 0, 0]

        # Convert to QImage
        image = numpy_bgr_to_qimage(frame)

        # QImage.pixelColor returns an RGBA colour
        colour = image.pixelColor(0, 0)

        # Check colour is blue
        assert colour.blue() == 255
        assert colour.red() == 0
        assert colour.green() == 0

    def test_rejects_4_channel(self, qapp):
        """A 4-channel array is not supported (we only handle BGR)."""
        from seavision.gui.shared.conversion import numpy_bgr_to_qimage
        import pytest

        frame = np.zeros((100, 100, 4), dtype=np.uint8)
        with pytest.raises(ValueError, match="channels"):
            numpy_bgr_to_qimage(frame)

    def test_rejects_2_channel(self, qapp):
        """A 2-channel array is not a valid image format."""
        from seavision.gui.shared.conversion import numpy_bgr_to_qimage
        import pytest

        frame = np.zeros((100, 100, 2), dtype=np.uint8)
        with pytest.raises(ValueError, match="channels"):
            numpy_bgr_to_qimage(frame)

    def test_rejects_1d_array(self, qapp):
        """A 1D array should be rejected."""
        from seavision.gui.shared.conversion import numpy_bgr_to_qimage
        import pytest

        frame = np.zeros((100,), dtype=np.uint8)
        with pytest.raises(ValueError):
            numpy_bgr_to_qimage(frame)

        