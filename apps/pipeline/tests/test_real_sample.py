"""Regression tests on real ECMWF files, skipped unless `make sample` has downloaded them."""

from pathlib import Path

import numpy as np
import pytest

from pf_pipeline.derive import plan_windows, windows_to_mm
from pf_pipeline.grib import decode_grib_file

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "raw" / "sample"
FILES = sorted(SAMPLES.glob("*_tp.grib2"))

pytestmark = pytest.mark.skipif(not FILES, reason="run `make sample` to download real files")


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_real_fields_pass_the_convention_guard(path):
    """Lossy GRIB packing makes dry cells decrease slightly; the guard must not mistake it for a
    wrong convention (it did with a fixed 0.05 mm tolerance on 12-bit IFS data)."""
    fields = list(decode_grib_file(path))
    acc = {f.step: f.values for f in fields}
    noise = {f.step: f.meta["packing_step_mm"] for f in fields}
    assert all(v > 0 for v in noise.values())
    windows = plan_windows(set(acc), 6, 48, 48)
    mm, q = windows_to_mm(acc, windows, noise)
    assert q.negative_fraction == 0.0
    assert np.isfinite(mm).all() and mm.max() > 10  # real storms exist in a global field
