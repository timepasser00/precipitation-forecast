"""From accumulated precipitation to the frames the app shows.

ECMWF total precipitation is accumulated from the start of the forecast, so rainfall over any
window is simply tp(end) - tp(start). A "frame" is one such window: a short interval (3 or 6
hours) in the fine part of the forecast, or a 24-hour total further out.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from .fields import PipelineError

NEGATIVE_TOLERANCE_MM = 0.05  # packing noise below this is clipped silently
NEGATIVE_FRACTION_LIMIT = 0.005  # more negative cells than this means the convention is wrong


class ConventionError(PipelineError):
    """tp does not behave like an accumulation from the forecast start."""


@dataclass(frozen=True)
class FrameWindow:
    start_h: int
    end_h: int
    kind: str  # "interval" | "daily"


@dataclass(frozen=True)
class Quality:
    frames: int
    max_mm: float
    wet_fraction: float
    negative_fraction: float


def plan_windows(
    steps_available: set[int], fine_step_h: int, fine_until_h: int, daily_until_h: int
) -> list[FrameWindow]:
    """Choose frame windows from the steps a run offers.

    Fine frames use every available step that is a multiple of ``fine_step_h`` up to
    ``fine_until_h``. After the last fine boundary, 24-hour windows continue while both ends are
    available and the end is within ``daily_until_h``.
    """
    fine = sorted(h for h in steps_available if 0 < h <= fine_until_h and h % fine_step_h == 0)
    points = [0, *fine]
    windows = [FrameWindow(a, b, "interval") for a, b in itertools.pairwise(points)]
    t = points[-1]
    while t + 24 <= daily_until_h and (t + 24) in steps_available:
        windows.append(FrameWindow(t, t + 24, "daily"))
        t += 24
    return windows


def required_steps(windows: list[FrameWindow]) -> set[int]:
    """Steps to download. Step 0 is zero by definition and never fetched."""
    return {w.end_h for w in windows} | {w.start_h for w in windows if w.start_h > 0}


def windows_to_mm(
    acc_m: dict[int, np.ndarray], windows: list[FrameWindow]
) -> tuple[np.ndarray, Quality]:
    """Accumulations (metres, by step) to per-window rainfall in mm, shape (frames, ny, nx)."""
    if not windows:
        raise PipelineError("no frame windows could be planned (steps missing?)")
    shape = next(iter(acc_m.values())).shape
    zero = np.zeros(shape, dtype=np.float32)
    out = np.empty((len(windows), *shape), dtype=np.float32)
    worst_neg = 0.0
    for i, w in enumerate(windows):
        start = acc_m[w.start_h] if w.start_h > 0 else zero
        d = (acc_m[w.end_h] - start) * np.float32(1000.0)
        worst_neg = max(worst_neg, float((d < -NEGATIVE_TOLERANCE_MM).mean()))
        out[i] = np.maximum(d, 0.0)
    if worst_neg > NEGATIVE_FRACTION_LIMIT:
        raise ConventionError(
            f"{worst_neg:.2%} of cells decrease between steps; tp does not look like an "
            "accumulation from forecast start. Run `pf-pipeline inspect` on a real file."
        )
    return out, Quality(
        frames=len(windows),
        max_mm=float(out.max()),
        wet_fraction=float((out >= 0.1).mean()),
        negative_fraction=worst_neg,
    )
