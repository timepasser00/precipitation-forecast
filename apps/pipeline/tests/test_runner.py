from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from pf_pipeline.adapters.synthetic import SyntheticAdapter
from pf_pipeline.fields import PipelineError
from pf_pipeline.runner import run_source
from precip_core.codec import Encoding, decode_atlas, decode_cube, dequantize
from precip_core.manifest import load_manifest, run_id
from precip_core.tiling import BilinearSampler, tile_axes

RUN = datetime(2026, 11, 5, 0, tzinfo=UTC)


class RealLooking(SyntheticAdapter):
    """Pretends to be a real source (synthetic = False) to test the mixing guard."""

    synthetic = False


def _publish(reg, storage, run=RUN, **kw):
    spec = reg.source("test-src")
    adapter = kw.pop("adapter", None) or SyntheticAdapter("test-src")
    return run_source(reg, spec, adapter, run, storage, **kw)


def test_publish_builds_manifest_tiles_and_cube(reg, storage):
    summary = _publish(reg, storage)
    assert set(summary) == {"t0", "t1"}
    m = load_manifest(storage)
    entry = m.sources["test-src"]
    rid = run_id(RUN)
    assert entry.latest == rid and entry.previous is None
    run = entry.runs[rid]
    assert run.status == "complete" and run.synthetic is True

    t0 = run.tiers["t0"]
    # 6-hourly to 24 h (4 frames) + one daily frame 24-48 h
    assert [f.kind for f in t0.frames] == ["interval"] * 4 + ["daily"]
    assert t0.frames[0].start == RUN and t0.frames[-1].end == RUN + timedelta(hours=48)
    assert t0.chunks == 2  # 5 frames, 4 per chunk
    assert sorted(t0.tiles) == ["0", "1"] and len(t0.tiles["1"]) == 4

    for z, xy in t0.tiles.items():
        for x, y in xy:
            for c in range(t0.chunks):
                key = t0.tile_path.format(z=z, x=x, y=y, chunk=c)
                assert storage.exists(key), key
    assert storage.exists(t0.cube_path) and storage.exists(run.tiers["t1"].cube_path)
    assert t0.bytes == sum(len(storage.get(k)) for k in storage.list(f"runs/test-src/{rid}/t0"))


def test_regional_tier_marks_outside_pixels_nodata(reg, storage):
    _publish(reg, storage)
    t1 = load_manifest(storage).sources["test-src"].runs[run_id(RUN)].tiers["t1"]
    ((x, y),) = t1.tiles["3"][:1]
    atlas = decode_atlas(storage.get(t1.tile_path.format(z=3, x=x, y=y, chunk=0)), 4, 2, tile=32)
    assert (atlas == 255).any()  # parts of the tile lie outside the India box
    assert (atlas < 255).any()


def test_cube_and_tile_agree_at_the_same_location(reg, storage):
    """The two products come from one field, so they must tell the same story."""
    _publish(reg, storage)
    m = load_manifest(storage)
    t0 = m.sources["test-src"].runs[run_id(RUN)].tiers["t0"]
    header, cube = decode_cube(storage.get(t0.cube_path))
    from precip_core.grid import GridSpec

    grid = GridSpec.from_dict(header["grid"])
    enc = Encoding(**header["encoding"])
    z, x, y = 1, 1, 0  # a northern-hemisphere tile
    lon, lat = tile_axes(z, x, y, 32)
    atlas = decode_atlas(storage.get(t0.tile_path.format(z=z, x=x, y=y, chunk=0)), 4, 2, tile=32)
    tile_mm = dequantize(atlas, enc)  # (4, 32, 32)
    cube_mm = dequantize(np.moveaxis(cube, 2, 0), enc)  # (frames, ny, nx)
    ref = BilinearSampler(grid, lon, lat).apply(cube_mm[:4])
    both_wet = (tile_mm > 0.5) & (ref > 0.5)
    assert both_wet.sum() > 20
    rel = np.abs(tile_mm - ref)[both_wet] / ref[both_wet]
    assert np.median(rel) < 0.05


def test_rerun_is_idempotent(reg, storage):
    _publish(reg, storage)
    before = {k: storage.get(k) for k in storage.list("runs")}
    _publish(reg, storage)
    assert {k: storage.get(k) for k in storage.list("runs")} == before
    assert list(load_manifest(storage).sources["test-src"].runs) == [run_id(RUN)]


def test_retention_keeps_latest_and_previous_only(reg, storage):
    runs = [RUN + timedelta(hours=6 * i) for i in range(3)]
    for r in runs:
        _publish(reg, storage, run=r)
    e = load_manifest(storage).sources["test-src"]
    assert e.latest == run_id(runs[2]) and e.previous == run_id(runs[1])
    assert set(e.runs) == {run_id(runs[1]), run_id(runs[2])}
    assert storage.list(f"runs/test-src/{run_id(runs[0])}") == []  # old objects deleted


def test_latest_only_moves_when_required_tiers_are_complete(reg, storage):
    first = RUN
    second = RUN + timedelta(hours=6)
    _publish(reg, storage, run=first)
    _publish(reg, storage, run=second, tiers={"t0"})  # t1 (required) still missing
    e = load_manifest(storage).sources["test-src"]
    assert e.latest == run_id(first) and e.runs[run_id(second)].status == "partial"
    _publish(reg, storage, run=second, tiers={"t1"})
    e = load_manifest(storage).sources["test-src"]
    assert e.latest == run_id(second) and e.previous == run_id(first)
    assert e.runs[run_id(second)].status == "complete"


def test_failure_midway_leaves_published_run_untouched(reg, storage):
    _publish(reg, storage)
    before = storage.get("manifest.json")

    class Flaky(SyntheticAdapter):
        def iter_fields(self, run_time, resolution, steps):
            for i, f in enumerate(super().iter_fields(run_time, resolution, steps)):
                if i == 2:
                    raise PipelineError("network dropped")
                yield f

    with pytest.raises(PipelineError):
        _publish(reg, storage, run=RUN + timedelta(hours=6), adapter=Flaky("test-src"))
    assert storage.get("manifest.json") == before


def test_refuses_to_mix_synthetic_and_real(reg, storage):
    _publish(reg, storage)
    with pytest.raises(PipelineError, match="refusing"):
        _publish(reg, storage, run=RUN + timedelta(hours=6), adapter=RealLooking("test-src"))


def test_wrong_grid_resolution_is_rejected(reg, storage):
    class WrongGrid(SyntheticAdapter):
        def iter_fields(self, run_time, resolution, steps):
            return super().iter_fields(run_time, "0p5", steps)  # not what was asked for

    with pytest.raises(PipelineError, match="expected"):
        _publish(reg, storage, adapter=WrongGrid("test-src"))


def test_unknown_run_hour_is_a_clear_error(reg, storage):
    with pytest.raises(ValueError, match="no step schedule"):
        _publish(reg, storage, run=datetime(2026, 11, 5, 3, tzinfo=UTC))
