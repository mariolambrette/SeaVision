"""Configuration for the Community Fish Detector (CFD) detector.

CFD is the marine analogue of MegaDetector: a single-class ("fish") object
detector. The current, non-deprecated models are RF-DETR checkpoints published
by the CFD project; the older YOLOv12x checkpoint is deprecated upstream (and
AGPL-licensed) and is deliberately not supported here.

Weights are pinned to a specific GitHub release rather than resolved as
"latest", so a run is reproducible: a new upstream release cannot silently
change results. To move to a newer release, bump ``release_tag`` (and the
per-variant filenames in ``CFD_WEIGHT_FILES`` if they change).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

# --- Pinned release ---------------------------------------------------------
# Matches the URLs hardcoded in the CFD repo's own test script
# (test_community_fish_detector.py) for the 2026.07.06 release.
CFD_RELEASE_TAG = "2026.07.06-release"
CFD_RELEASE_BASE = (
    "https://github.com/filippovarini/community-fish-detector/"
    "releases/download/{tag}/"
)

# variant -> checkpoint filename within the release.
CFD_WEIGHT_FILES: Dict[str, str] = {
    "nano": "cfd-rf-detr-nano-640-2026.02.02.cp-011.20260706-release.pth",
    "small": "cfd-rf-detr-small-1024-2026.06.06.cp-016.20260706-release.pth",
    "medium": "cfd-rf-detr-medium-1024-2026.03.24.cp-011.20260706-release.pth",
}

# Reported AP on the CFD validation split. Only useful for ranking the CFD
# variants against each other; the absolute values are not comparable to any
# other benchmark (see the CFD README). medium 0.609 > small 0.606 > nano 0.596
# is within noise on their split — do not over-read the medium/small gap.
CFD_VARIANT_AP: Dict[str, float] = {"nano": 0.596, "small": 0.606, "medium": 0.609}


@dataclass
class CFDDetectorConfig:
    """Configuration for :class:`CFDDetector`.

    Attributes:
        variant: RF-DETR size, one of ``"nano"``, ``"small"``, ``"medium"``.
            This is the accuracy/speed lever. ``nano`` runs at 640 px,
            ``small``/``medium`` at 1024 px (resolved from the checkpoint).
        device: Compute device string, e.g. ``"cuda:0"`` or ``"cpu"``.
        threshold: Confidence floor applied by ``predict()``.
        resolution: Optional inference resolution override (square). ``None``
            uses the training resolution recorded in the checkpoint, which is
            the correct default and needs no manual ``imgsz`` plumbing. If set,
            it must be divisible by ``patch_size * num_windows`` (32 for these
            RF-DETR variants) or ``predict()`` will raise. It is NOT RECCOMENDED
            to override this unless you have a specific reason.
        output_labels: If True, emit the model's class name as the detection
            label (``"fish"``). CFD is single-class, so this is constant.
        weights_path: Explicit local ``.pth`` path. If set and it exists, it is
            used directly and no download occurs (overrides ``variant``).
        weights_url: Explicit download URL. If set, overrides the URL resolved
            from ``variant`` + ``release_tag``.
        release_tag: GitHub release tag to pull weights from.
        persist_weights: If True (default), cache the downloaded checkpoint to
            ``cache_dir`` and skip the download on subsequent runs. If False,
            download to a temporary file, load, then delete it — no persistent
            disk footprint, at the cost of re-downloading every process start.
        cache_dir: Directory for the cached checkpoint when
            ``persist_weights`` is True. ``None`` uses
            ``<tempdir>/community-fish-detector``.
        optimize_for_inference: Call ``model.optimize_for_inference()`` after
            load. Off by default, mirroring the CFD repo — its bfloat16 path is
            reported to produce degenerate boxes.
    """

    variant: str = "medium"
    device: str = "cuda:0"
    threshold: float = 0.001
    resolution: Optional[int] = None
    output_labels: bool = True

    # Weight source / caching
    weights_path: Optional[str] = None
    weights_url: Optional[str] = None
    release_tag: str = CFD_RELEASE_TAG
    persist_weights: bool = True
    cache_dir: Optional[str] = None

    # Runtime
    optimize_for_inference: bool = False

    def __post_init__(self) -> None:
        if self.variant not in CFD_WEIGHT_FILES:
            raise ValueError(
                f"Unknown CFD variant {self.variant!r}. "
                f"Valid variants: {sorted(CFD_WEIGHT_FILES)}."
            )

    def resolve_weights_url(self) -> str:
        """Return the download URL for the configured variant/release."""
        if self.weights_url:
            return self.weights_url
        base = CFD_RELEASE_BASE.format(tag=self.release_tag)
        return base + CFD_WEIGHT_FILES[self.variant]