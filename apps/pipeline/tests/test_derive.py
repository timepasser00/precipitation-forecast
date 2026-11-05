import numpy as np
import pytest

from pf_pipeline.derive import (
    ConventionError,
    FrameWindow,
    plan_windows,
    required_steps,
    windows_to_mm,
)

IFS_00 = set(range(0, 145, 3)) | set(range(150, 361, 6))
IFS_06 = set(range(0, 91, 3))
AIFS = set(range(0, 361, 6))


def test_ifs_00z_global_tier_is_6_hourly_then_daily():
    w = plan_windows(IFS_00, 6, 168, 360)
    fine = [x for x in w if x.kind == "interval"]
    daily = [x for x in w if x.kind == "daily"]
    assert len(fine) == 28 and fine[0] == FrameWindow(0, 6, "interval")
    assert fine[-1] == FrameWindow(162, 168, "interval")
    assert len(daily) == 8 and daily[0] == FrameWindow(168, 192, "daily")
    assert daily[-1] == FrameWindow(336, 360, "daily")


def test_ifs_00z_regional_tier_is_3_hourly_early_then_6_hourly():
    w = plan_windows(IFS_00, 3, 168, 360)
    assert w[0] == FrameWindow(0, 3, "interval")
    assert FrameWindow(144, 150, "interval") in w  # native cadence switches to 6 h
    assert sum(x.kind == "interval" for x in w) == 48 + 4


def test_short_run_has_no_daily_frames():
    w = plan_windows(IFS_06, 3, 168, 360)
    assert all(x.kind == "interval" for x in w) and w[-1].end_h == 90


def test_aifs_tier_cadence_is_limited_by_the_source():
    w = plan_windows(AIFS, 3, 168, 360)
    assert w[0] == FrameWindow(0, 6, "interval") and sum(x.kind == "interval" for x in w) == 28


def test_detail_only_tier_has_no_daily():
    w = plan_windows(IFS_00, 3, 144, 144)
    assert len(w) == 48 and w[-1].end_h == 144


def test_required_steps_skip_zero():
    assert required_steps([FrameWindow(0, 6, "interval"), FrameWindow(6, 12, "interval")]) == {
        6,
        12,
    }


def test_windows_to_mm_differences_and_units():
    shape = (2, 3)
    acc = {6: np.full(shape, 0.002, np.float32), 12: np.full(shape, 0.005, np.float32)}
    w = [FrameWindow(0, 6, "interval"), FrameWindow(6, 12, "interval")]
    mm, q = windows_to_mm(acc, w)
    assert mm.shape == (2, 2, 3)
    assert np.allclose(mm[0], 2.0) and np.allclose(mm[1], 3.0)
    assert q.max_mm == pytest.approx(3.0) and q.wet_fraction == 1.0


def test_tiny_negative_packing_noise_is_clipped():
    acc = {6: np.full((4, 4), 0.003, np.float32), 12: np.full((4, 4), 0.003 - 1e-5, np.float32)}
    mm, _ = windows_to_mm(acc, [FrameWindow(0, 6, "interval"), FrameWindow(6, 12, "interval")])
    assert mm.min() == 0.0


def test_decreasing_accumulation_is_rejected():
    rng = np.random.default_rng(0)
    a6 = rng.random((50, 50), dtype=np.float32) * 0.01
    a12 = rng.random((50, 50), dtype=np.float32) * 0.01  # per-interval values, not accumulations
    with pytest.raises(ConventionError):
        windows_to_mm(
            {6: a6, 12: a12}, [FrameWindow(0, 6, "interval"), FrameWindow(6, 12, "interval")]
        )


def _packed_pair(step_mm: float):
    """Two accumulations of a mostly dry field whose second one is off by 1.5 packing steps."""
    a6 = np.full((100, 100), 0.002, np.float32)
    a12 = a6 - np.float32(1.5 * step_mm / 1000)
    return {6: a6, 12: a12}


def test_packing_noise_is_tolerated_when_the_packing_step_is_known():
    w = [FrameWindow(0, 6, "interval"), FrameWindow(6, 12, "interval")]
    acc = _packed_pair(0.1)  # a decrease of 0.15 mm everywhere
    with pytest.raises(ConventionError):
        windows_to_mm(acc, w)  # unexplained without the packing step
    mm, q = windows_to_mm(acc, w, {6: 0.1, 12: 0.1})  # explained: tolerance is 0.2 mm
    assert mm[1].max() == 0.0 and q.negative_fraction == 0.0


def test_a_wrong_convention_is_still_rejected_despite_packing_tolerance():
    rng = np.random.default_rng(1)
    a6 = rng.random((50, 50), dtype=np.float32) * 0.01
    a12 = rng.random((50, 50), dtype=np.float32) * 0.01
    with pytest.raises(ConventionError):
        windows_to_mm(
            {6: a6, 12: a12},
            [FrameWindow(0, 6, "interval"), FrameWindow(6, 12, "interval")],
            {6: 0.1, 12: 0.1},
        )
