"""Mock-based tests for CFDDetector.

No torch / rfdetr / GPU / network required. A fake ``rfdetr`` module is injected
into sys.modules so we exercise the SeaVision wrapper's own logic: lazy import,
BGR->RGB handling, box/label/confidence conversion, and single-image unwrap.
End-to-end (real weights + GPU) is a separate check to run on the workstation.
"""

import sys
import types
import numpy as np
import pytest


# --- Fixtures --------------------------------------------------------------

@pytest.fixture
def tmp_weights(tmp_path):
    """A dummy local checkpoint file so _resolve_weights takes the
    'existing local file' branch and never attempts a download."""
    path = tmp_path / "cfd-fake.pth"
    path.write_bytes(b"fake checkpoint")
    return str(path)


# --- Fake rfdetr -----------------------------------------------------------

class _FakeDetections:
    """Minimal stand-in for supervision.Detections."""
    def __init__(self, xyxy, confidence, class_id):
        self.xyxy = np.asarray(xyxy, dtype=float)
        self.confidence = np.asarray(confidence, dtype=float)
        self.class_id = np.asarray(class_id, dtype=int)

    def __len__(self):
        return len(self.xyxy)


class _FakeModel:
    resolution = 1024
    class_names = ["fish"]

    def __init__(self):
        self.last_input = None
        self.last_kwargs = None

    def predict(self, image, **kwargs):
        # Record what the wrapper actually passed so the test can assert on it.
        self.last_input = image
        self.last_kwargs = kwargs
        # One box: xyxy (10,20,110,220) -> xc=60,yc=120,w=100,h=200.
        return _FakeDetections(
            xyxy=[[10.0, 20.0, 110.0, 220.0]],
            confidence=[0.87],
            class_id=[0],
        )


_LOADED = {}


def _install_fake_rfdetr():
    mod = types.ModuleType("rfdetr")

    def from_checkpoint(path, **kwargs):
        _LOADED["path"] = path
        _LOADED["kwargs"] = kwargs
        return _FakeModel()

    mod.from_checkpoint = from_checkpoint #type: ignore
    sys.modules["rfdetr"] = mod


# --- Tests -----------------------------------------------------------------

def test_lazy_import():
    """Importing the detector must NOT import rfdetr (it isn't installed here;
    a module-level import would raise). Reaching import time proves laziness."""
    sys.modules.pop("rfdetr", None)
    import seavision.engine.detectors.cfd.detector  # noqa: F401
    assert "rfdetr" not in sys.modules, "rfdetr imported too early (not lazy)"
    print("PASS lazy import")


def test_variant_url_resolution():
    from seavision.engine.detectors.cfd import CFDDetectorConfig
    cfg = CFDDetectorConfig(variant="medium")
    url = cfg.resolve_weights_url()
    assert url.endswith("cfd-rf-detr-medium-1024-2026.03.24.cp-011.20260706-release.pth"), url
    assert "2026.07.06-release" in url, url
    # bad variant rejected at construction
    try:
        CFDDetectorConfig(variant="xlarge")
    except ValueError:
        pass
    else:
        raise AssertionError("bad variant not rejected")
    print("PASS variant/URL resolution")


def test_process_frame_conversion(tmp_weights):
    _install_fake_rfdetr()
    from seavision.engine.detectors.cfd import CFDDetector, CFDDetectorConfig
    from seavision.engine.source import FrameContext

    cfg = CFDDetectorConfig(
        variant="medium",
        device="cpu",
        weights_path=tmp_weights,   # existing local file -> no download
        threshold=0.001,
    )
    det = CFDDetector(cfg)

    # Frame with a distinctive BGR pixel: pure red in BGR is (0,0,255).
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[0, 0] = (0, 0, 255)  # BGR red
    ctx = FrameContext(source_file="clip.mp4", frame_number=7, timestamp=0.25, fps=28.0)

    results = list(det.process_frame(frame, ctx))

    # 1. The model received RGB: BGR (0,0,255) -> RGB (255,0,0).
    seen = det._model.last_input #type: ignore
    assert seen[0, 0].tolist() == [255, 0, 0], seen[0, 0].tolist()
    # 2. Contiguous buffer (torch.from_numpy would reject negative strides).
    assert seen.flags["C_CONTIGUOUS"], "input to predict() not contiguous"
    # 3. source image copy suppressed.
    assert det._model.last_kwargs.get("include_source_image") is False #type: ignore
    # 4. device forwarded to from_checkpoint.
    assert _LOADED["kwargs"].get("device") == "cpu", _LOADED["kwargs"]

    # 5. Box conversion xyxy -> centre form.
    assert len(results) == 1
    d = results[0]
    assert (d.xc, d.yc, d.width, d.height) == (60.0, 120.0, 100.0, 200.0), \
        (d.xc, d.yc, d.width, d.height)
    assert d.bbox == (10.0, 20.0, 110.0, 220.0), d.bbox
    # 6. Confidence + label + provenance.
    assert d.confidence == 0.87
    assert d.label == "fish"
    assert d.source_file == "clip.mp4" and d.frame_number == 7 and d.timestamp == 0.25
    print("PASS process_frame conversion (BGR->RGB, box, label, conf, device)")


def test_resolution_override(tmp_weights):
    _install_fake_rfdetr()
    from seavision.engine.detectors.cfd import CFDDetector, CFDDetectorConfig
    from seavision.engine.source import FrameContext

    cfg = CFDDetectorConfig(variant="nano", device="cpu",
                            weights_path=tmp_weights, resolution=640)
    det = CFDDetector(cfg)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    ctx = FrameContext("v", 0, 0.0, 30.0)
    list(det.process_frame(frame, ctx))
    assert det._model.last_kwargs.get("shape") == (640, 640), det._model.last_kwargs #type: ignore
    print("PASS resolution override -> predict(shape=...)")


def test_no_shape_when_unset(tmp_weights): #pylint: disable=all
    _install_fake_rfdetr()
    from seavision.engine.detectors.cfd import CFDDetector, CFDDetectorConfig #pylint: disable=import-outside-toplevel
    from seavision.engine.source import FrameContext #pylint: disable=import-outside-toplevel

    cfg = CFDDetectorConfig(variant="medium", device="cpu", weights_path=tmp_weights)
    det = CFDDetector(cfg)
    list(det.process_frame(np.zeros((50, 50, 3), np.uint8),
                           FrameContext("v", 0, 0.0, 30.0)))
    assert "shape" not in det._model.last_kwargs, det._model.last_kwargs #type: ignore #pylint: disable=protected-access
    print("PASS resolution=None -> checkpoint resolution used (no shape passed)")


def test_lazy_registration():
    """CFDDetector must resolve via the package lazy loader."""
    import seavision.engine.detectors as d #pylint: disable=import-outside-toplevel
    assert d.CFD_AVAILABLE is True
    assert d.CFDDetector.__name__ == "CFDDetector" #type: ignore
    print("PASS package-level lazy registration")


if __name__ == "__main__":
    import tempfile, os #pylint: disable=import-outside-toplevel #pylint: disable=multiple-imports
    fd, tmp = tempfile.mkstemp(suffix=".pth"); os.close(fd)
    try:
        test_lazy_import()
        test_variant_url_resolution()
        test_process_frame_conversion(tmp)
        test_resolution_override(tmp)
        test_no_shape_when_unset(tmp)
        test_lazy_registration()
        print("\nALL TESTS PASSED")
    finally:
        os.remove(tmp)
