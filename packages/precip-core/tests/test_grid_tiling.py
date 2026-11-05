import numpy as np
import pytest

from precip_core.grid import GridSpec, coarsen2, crop_grid, global_grid, res_from_code
from precip_core.tiling import BilinearSampler, tile_axes, tiles_for_bbox


def test_res_from_code():
    assert res_from_code("0p25") == 0.25
    assert res_from_code("0p1") == 0.1
    assert res_from_code("2p0") == 2.0


def test_global_grid_shape():
    g = global_grid(0.25)
    assert g.shape == (721, 1440) and g.wrap_lon
    assert g.lats[0] == 90 and g.lats[-1] == -90 and g.lons[-1] == 359.75


def test_crop_grid_contains_bbox_with_margin():
    g = global_grid(0.25)
    sub, rs, cs = crop_grid(g, (67, 6, 98, 38))
    assert sub.lat0 >= 38 and sub.lats[-1] <= 6
    assert sub.lons[0] <= 67 and sub.lons[-1] >= 98
    assert sub.shape == (rs.stop - rs.start, cs.stop - cs.start)
    assert not sub.wrap_lon


def test_crop_grid_global_is_identity():
    g = global_grid(0.5)
    sub, rs, cs = crop_grid(g, (-180, -90, 180, 90))
    assert sub is g and rs == slice(None) and cs == slice(None)


def test_coarsen2_keeps_mean_and_shape():
    g = global_grid(0.25)
    rng = np.random.default_rng(1)
    f = rng.random(g.shape, dtype=np.float32)
    c, cg = coarsen2(f, g)
    assert cg.shape == (361, 720) and cg.dlat == 0.5
    assert abs(float(c.mean()) - float(f.mean())) < 0.01


def test_coarsen2_rejects_regional_grid():
    g = GridSpec(40, 60, 0.25, 0.25, 100, 100, wrap_lon=False)
    with pytest.raises(ValueError):
        coarsen2(np.zeros(g.shape, np.float32), g)


def test_tiles_for_bbox_known_values():
    assert tiles_for_bbox(0, (-180, -90, 180, 90)) == [(0, 0)]
    assert len(tiles_for_bbox(2, (-180, -90, 180, 90))) == 16
    # India at zoom 4: x 10..12, y 6..7 (checked by hand)
    assert tiles_for_bbox(4, (67, 6, 98, 38)) == [(x, y) for y in (6, 7) for x in (10, 11, 12)]


def test_tile_axes_orientation_and_range():
    lon, lat = tile_axes(3, 5, 3)
    assert lon[0] < lon[-1] and lat[0] > lat[-1]
    assert lon[0] >= -180 + 5 * 45 and lon[-1] <= -180 + 6 * 45


def test_bilinear_reproduces_linear_field_and_wraps():
    g = global_grid(1.0)
    lat = g.lats[:, None]
    lon = g.lons[None, :]
    field = (0.1 * lat + 0.0 * lon).astype(np.float32)  # varies with latitude only
    s = BilinearSampler(g, np.array([10.5, 359.5, -0.5]), np.array([40.25, -12.75]))
    out = s.apply(field)
    expected = 0.1 * np.array([40.25, -12.75])[:, None] * np.ones((1, 3))
    assert np.allclose(out, expected, atol=1e-4)


def test_bilinear_marks_outside_regional_grid_nan():
    g = GridSpec(40, 60, 1.0, 1.0, 11, 11, wrap_lon=False)  # lat 40..30, lon 60..70
    s = BilinearSampler(g, np.array([65.0, 80.0]), np.array([35.0, 50.0]))
    out = s.apply(np.ones(g.shape, np.float32))
    assert out[0, 0] == pytest.approx(1.0)
    assert np.isnan(out[0, 1]) and np.isnan(out[1, 0]) and np.isnan(out[1, 1])


def test_bilinear_works_on_stacks():
    g = global_grid(2.0)
    stack = np.stack([np.full(g.shape, 1.0, np.float32), np.full(g.shape, 2.0, np.float32)])
    lon, lat = tile_axes(1, 0, 0, 16)
    out = BilinearSampler(g, lon, lat).apply(stack)
    assert out.shape == (2, 16, 16)
    assert np.allclose(out[0], 1) and np.allclose(out[1], 2)
