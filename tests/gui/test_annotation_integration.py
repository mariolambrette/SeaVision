"""Tests for worker annotation logic."""

import numpy as np

from seavision.engine.detectors.base import Detection
from seavision.engine.visualiser import FrameAnnotator
from seavision.engine.visualiser.loader import ListDetectionSource


class TestAnnotationIntegration:
    """Verify FrameAnnotator works with detection sources."""

    def test_annotator_with_detections(self):
        """Annotating a frame with detections should modify pixels."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        det = Detection(
            source_file="test.ts",
            timestamp=1.0,
            frame_number=10,
            xc=320.0, yc=240.0,
            width=100.0, height=80.0,
            confidence=0.9,
            label="fish",
        )

        annotator = FrameAnnotator()
        annotated = annotator.annotate_frame(frame, [det], copy=True)

        # The annotated frame should differ from the original
        # (bounding box pixels are non-zero)
        assert not np.array_equal(frame, annotated)

    def test_annotator_without_detections(self):
        """Annotating with an empty list should return an identical frame."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        annotator = FrameAnnotator()
        annotated = annotator.annotate_frame(frame, [], copy=True)

        assert np.array_equal(frame, annotated)

    def test_detection_source_lookup(self):
        """ListDetectionSource should return correct detections per frame."""
        dets = [
            Detection(
                source_file="test.ts", timestamp=1.0, frame_number=10,
                xc=100, yc=100, width=50, height=50,
            ),
            Detection(
                source_file="test.ts", timestamp=2.0, frame_number=20,
                xc=200, yc=200, width=60, height=60,
            ),
        ]

        source = ListDetectionSource(dets, "test.ts")

        assert len(source.get_detections_for_frame(10)) == 1
        assert len(source.get_detections_for_frame(20)) == 1
        assert len(source.get_detections_for_frame(15)) == 0