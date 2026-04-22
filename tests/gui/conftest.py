"""
Shared fixtures for SeaVIsion GUI tests.

Provides:
    qapp: Session-scoped QApplication instance.
    sample_detection: Function-scoped list of Detection objects for model
        tests.
    sample_videp_path: Session-scoped path to a .ts test files (skips if
        absent).
"""

from pathlib import Path
from typing import List

import pytest

from seavision.engine.detectors.base import Detection


@pytest.fixture(scope="session")
def qapp():
    """
    Create a QApplication instance for the entire test session.

    Many Qt classes require a QApplication to exist before they can be
    initialised, even when no window is shown. Session-scoped so it is created
    once and shared between tests. The instance() guard avoids creating a
    second QApplication if one already exists (e.g. from a pytest plugin).
    """

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# Fake video file strings
_VIDEO_A = "fake/file_A.ts"
_VIDEO_B = "fake/file_B.ts"


@pytest.fixture
def sample_detections() -> List[Detection]:
    """
    Return a fresh list of 10 Detection objects for testing.

    Spread across 4 frame numbers and 2 source videos, with varied confidence,
    labels, and track IDs. Function-scoped so each test gets an idependent copy.

    Layout:
        Video A — frames 10, 25, 25, 42       (4 detections)
        Video B — frames 5, 5, 18, 18, 30, 30 (6 detections)
    """
    return [
        # --- Video A detections ---
        Detection(
            source_file=_VIDEO_A,
            timestamp=1.0,
            frame_number=10,
            xc=320.0, yc=240.0, width=40.0, height=30.0,
            confidence=0.92,
            label="fish",
            track_id=1,
        ),
        Detection(
            source_file=_VIDEO_A,
            timestamp=2.5,
            frame_number=25,
            xc=150.0, yc=300.0, width=60.0, height=55.0,
            confidence=0.78,
            label="fish",
            track_id=2,
        ),
        Detection(
            source_file=_VIDEO_A,
            timestamp=2.5,
            frame_number=25,
            xc=400.0, yc=100.0, width=25.0, height=20.0,
            confidence=0.45,
            label="motion",
            track_id=None,
        ),
        Detection(
            source_file=_VIDEO_A,
            timestamp=4.2,
            frame_number=42,
            xc=500.0, yc=350.0, width=80.0, height=70.0,
            confidence=0.88,
            label="turtle",
            track_id=3,
        ),
        # --- Video B detections ---
        Detection(
            source_file=_VIDEO_B,
            timestamp=0.5,
            frame_number=5,
            xc=100.0, yc=200.0, width=35.0, height=30.0,
            confidence=0.65,
            label="motion",
            track_id=None,
        ),
        Detection(
            source_file=_VIDEO_B,
            timestamp=0.5,
            frame_number=5,
            xc=450.0, yc=220.0, width=50.0, height=45.0,
            confidence=0.71,
            label="fish",
            track_id=4,
        ),
        Detection(
            source_file=_VIDEO_B,
            timestamp=1.8,
            frame_number=18,
            xc=200.0, yc=150.0, width=30.0, height=25.0,
            confidence=0.33,
            label="motion",
            track_id=None,
        ),
        Detection(
            source_file=_VIDEO_B,
            timestamp=1.8,
            frame_number=18,
            xc=380.0, yc=400.0, width=90.0, height=80.0,
            confidence=0.95,
            label="whale",
            track_id=5,
        ),
        Detection(
            source_file=_VIDEO_B,
            timestamp=3.0,
            frame_number=30,
            xc=300.0, yc=240.0, width=45.0, height=40.0,
            confidence=0.82,
            label="fish",
            track_id=6,
        ),
        Detection(
            source_file=_VIDEO_B,
            timestamp=3.0,
            frame_number=30,
            xc=550.0, yc=100.0, width=20.0, height=15.0,
            confidence=0.29,
            label="motion",
            track_id=None,
        ),
    ]


# Path to a sample .ts video file for testing video loading.
# TODO: Add a small .ts file to the repo for this purpose, and update the path as needed.
_TEST_VIDEO_DIR = Path(__file__).resolve().parent.parent / "data"
_TEST_VIDEO_PATH = _TEST_VIDEO_DIR / "sample.ts"


@pytest.fixture(scope="session")
def sample_video_path() -> Path:
    """
    Return the path to a short .ts video file.
    
    If the file does not exist, the test is skipped automatically.
    To enable video-dependant tests, place a short clip at:
        tests/data/sample.ts
    """
    if not _TEST_VIDEO_PATH.exists():
        pytest.skip(
            f"Sample video file not found at {_TEST_VIDEO_PATH}. "
            "Place a short .ts vlip there to enable video tests."
        )
    return _TEST_VIDEO_PATH
