"""Tests for edge ONNX pre/postprocessing."""

import numpy as np
import pytest

from seavision.edge.postprocess import (
    letterbox,
    preprocess,
    postprocess,
    scale_boxes_to_original,
)


class TestLetterbox:
    """Test the letterbox resize function."""

    def test_square_image_no_padding(self):
        img = np.zeros((640, 640, 3), dtype=np.uint8)
        result, ratio, pad = letterbox(img, (640, 640))
        assert result.shape == (640, 640, 3)
        assert ratio == 1.0

    def test_landscape_image_padded(self):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        result, ratio, pad = letterbox(img, (640, 640))
        assert result.shape == (640, 640, 3)
        assert ratio == pytest.approx(1.0, abs=0.01)

    def test_portrait_image_padded(self):
        img = np.zeros((640, 480, 3), dtype=np.uint8)
        result, ratio, pad = letterbox(img, (640, 640))
        assert result.shape == (640, 640, 3)

    def test_small_image_upscaled(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result, ratio, pad = letterbox(img, (640, 640))
        assert result.shape == (640, 640, 3)
        assert ratio > 1.0


class TestPreprocess:
    """Test the full preprocessing pipeline."""

    def test_output_shape(self):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        blob, ratio, pad = preprocess(img, 640)
        assert blob.shape == (1, 3, 640, 640)
        assert blob.dtype == np.float32

    def test_output_range(self):
        img = np.full((640, 640, 3), 255, dtype=np.uint8)
        blob, _, _ = preprocess(img, 640)
        assert blob.max() <= 1.0
        assert blob.min() >= 0.0

    def test_320_size(self):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        blob, _, _ = preprocess(img, 320)
        assert blob.shape == (1, 3, 320, 320)


class TestPostprocess:
    """Test YOLO output postprocessing."""

    def test_empty_output(self):
        # Simulate YOLO output with no confident detections
        # Shape: [1, 84, 100] — 80 classes + 4 box coords, 100 candidates
        output = [np.zeros((1, 84, 100), dtype=np.float32)]
        result = postprocess(output, conf_threshold=0.25)
        assert result == []

    def test_single_detection(self):
        # Create a fake output with one confident detection
        num_candidates = 10
        output_data = np.zeros((1, 84, num_candidates), dtype=np.float32)

        # First candidate: box at centre, high score for class 0
        output_data[0, 0, 0] = 320.0  # cx
        output_data[0, 1, 0] = 320.0  # cy
        output_data[0, 2, 0] = 100.0  # w
        output_data[0, 3, 0] = 100.0  # h
        output_data[0, 4, 0] = 0.9    # class 0 score

        result = postprocess([output_data], conf_threshold=0.25)
        assert len(result) == 1

        x1, y1, x2, y2, conf, cls_id = result[0]
        assert cls_id == 0
        assert conf == pytest.approx(0.9, abs=0.01)
        assert x1 == pytest.approx(270.0, abs=1.0)
        assert y1 == pytest.approx(270.0, abs=1.0)


class TestScaleBoxes:
    """Test coordinate scaling from letterbox to original frame."""

    def test_identity_scaling(self):
        dets = [(10.0, 20.0, 50.0, 60.0, 0.9, 0)]
        scaled = scale_boxes_to_original(dets, ratio=1.0, pad=(0.0, 0.0))
        assert scaled[0][:4] == (10.0, 20.0, 50.0, 60.0)

    def test_half_scale(self):
        dets = [(100.0, 100.0, 200.0, 200.0, 0.8, 1)]
        scaled = scale_boxes_to_original(dets, ratio=0.5, pad=(0.0, 0.0))
        x1, y1, x2, y2, conf, cls = scaled[0]
        assert x1 == pytest.approx(200.0)
        assert y1 == pytest.approx(200.0)
        assert x2 == pytest.approx(400.0)
        assert y2 == pytest.approx(400.0)