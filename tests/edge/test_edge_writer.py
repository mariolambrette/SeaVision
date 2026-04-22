"""Tests for the edge detection CSV writer."""

import csv
import pytest
from pathlib import Path

from seavision.edge.writer import EdgeDetectionWriter, CSV_COLUMNS


class TestEdgeDetectionWriter:
    """Test the edge CSV writer."""

    def test_creates_csv_with_header(self, tmp_path):
        with EdgeDetectionWriter(str(tmp_path), source_name="test") as writer:
            pass  # Just open and close

        csv_files = list(tmp_path.glob("detections_*.csv"))
        assert len(csv_files) == 1

        with open(csv_files[0]) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == CSV_COLUMNS

    def test_writes_detections(self, tmp_path):
        detections = [
            (100.0, 200.0, 150.0, 250.0, 0.85, 0),
            (300.0, 400.0, 350.0, 450.0, 0.72, 1),
        ]
        class_names = {0: "fish", 1: "seal"}

        with EdgeDetectionWriter(str(tmp_path), source_name="test") as writer:
            writer.write(detections, frame_number=42, timestamp=1.68,
                         class_names=class_names)

        csv_files = list(tmp_path.glob("detections_*.csv"))
        with open(csv_files[0]) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["frame_number"] == "42"
        assert rows[0]["label"] == "fish"
        assert rows[1]["label"] == "seal"

        # Check xc,yc,w,h conversion from xyxy
        # x1=100, y1=200, x2=150, y2=250 -> xc=125, yc=225, w=50, h=50
        assert float(rows[0]["xc"]) == pytest.approx(125.0, abs=0.5)
        assert float(rows[0]["yc"]) == pytest.approx(225.0, abs=0.5)
        assert float(rows[0]["width"]) == pytest.approx(50.0, abs=0.5)
        assert float(rows[0]["height"]) == pytest.approx(50.0, abs=0.5)

    def test_flush_interval(self, tmp_path):
        """Writer should flush after N frames."""
        with EdgeDetectionWriter(
            str(tmp_path), source_name="test", flush_interval=2
        ) as writer:
            writer.write(
                [(10.0, 20.0, 30.0, 40.0, 0.5, 0)],
                frame_number=0,
            )
            # After 1 frame, buffer is not flushed yet
            assert len(writer._buffer) == 1

            writer.write(
                [(10.0, 20.0, 30.0, 40.0, 0.5, 0)],
                frame_number=1,
            )
            # After 2 frames (= flush_interval), buffer should be flushed
            assert len(writer._buffer) == 0