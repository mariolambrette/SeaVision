"""
SeaVision edge inference runtime.

Lightweight inference package for edge devices (Raspberry Pi, Jetson,
etc.). Runs ONNX models with minimal dependencies — no PyTorch, no
Ultralytics.

Public API:
- EdgeConfig: Runtime configuration (always importable).
- EdgeRuntime: Main inference loop (requires onnxruntime at access time).
- FrameCapture: Video/camera input (requires opencv).
- EdgeDetectionWriter: CSV output (no special dependencies).
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .config import EdgeConfig

if TYPE_CHECKING:
    # Only imported during type checking, not at runtime.
    # Keeps onnxruntime optional on the land-side tooling.
    from .runtime import EdgeRuntime

# EdgeRuntime is imported lazily because it depends on onnxruntime,
# which is only installed on the edge device. This allows the land-side
# export tooling to import seavision.edge (for EdgeConfig and
# artifact builders) without requiring onnxruntime.


def __getattr__(name: str):
    if name == "EdgeRuntime":
        from .runtime import EdgeRuntime
        return EdgeRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["EdgeConfig", "EdgeRuntime"]