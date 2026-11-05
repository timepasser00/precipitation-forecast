from datetime import UTC, datetime

import eccodes
import numpy as np
import pytest

from pf_pipeline.grib import GribError, decode_grib_bytes, decode_grib_file, write_grib_message
from pf_pipeline.synth import SyntheticModel
from precip_core.grid import global_grid

RUN = datetime(2026, 11, 5, 6, tzinfo=UTC)


def _field(grid):
    lat, lon = grid.lats[:, None], grid.lons[None, :]
    return (0.01 + 0.002 * np.sin(np.radians(lon)) * np.cos(np.radians(lat))).astype(np.float32)


def test_grib_roundtrip_preserves_values_and_metadata():
    g = global_grid(2.0)
    f = _field(g)
    out = decode_grib_bytes(write_grib_message(f, g, 24, RUN))
    assert out.step == 24 and out.run_time == RUN and out.grid == g
    assert np.abs(out.values - f).max() < 1e-5  # well under 0.01 mm


def test_decode_file_yields_only_tp(tmp_path):
    g = global_grid(2.0)
    p = tmp_path / "x.grib2"
    p.write_bytes(
        write_grib_message(_field(g), g, 6, RUN) + write_grib_message(_field(g), g, 12, RUN)
    )
    assert [f.step for f in decode_grib_file(p)] == [6, 12]


def _raw_message(arr, *, lon_first, lon_last, j_positive, step_type="accum", units_param=228):
    gid = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    ny, nx = arr.shape
    for k, v in [
        ("Ni", nx), ("Nj", ny), ("paramId", units_param), ("dataDate", 20261105), ("dataTime", 0),
        ("stepType", step_type), ("startStep", 0), ("endStep", 6), ("bitsPerValue", 16),
        ("longitudeOfFirstGridPointInDegrees", lon_first),
        ("longitudeOfLastGridPointInDegrees", lon_last),
        ("iDirectionIncrementInDegrees", 2.0), ("jDirectionIncrementInDegrees", 2.0),
    ]:  # fmt: skip
        eccodes.codes_set(gid, k, v)
    if j_positive:
        eccodes.codes_set(gid, "latitudeOfFirstGridPointInDegrees", -90.0)
        eccodes.codes_set(gid, "latitudeOfLastGridPointInDegrees", 90.0)
        eccodes.codes_set(gid, "jScansPositively", 1)
    else:
        eccodes.codes_set(gid, "latitudeOfFirstGridPointInDegrees", 90.0)
        eccodes.codes_set(gid, "latitudeOfLastGridPointInDegrees", -90.0)
    eccodes.codes_set_values(gid, arr.astype(np.float64).ravel())
    data = eccodes.codes_get_message(gid)
    eccodes.codes_release(gid)
    return data


def test_decoder_normalises_scanning_and_longitude_origin():
    """A -180..180, south-to-north file must come out north-to-south from 0 degrees east."""
    g = global_grid(2.0)
    f = _field(g)  # canonical orientation
    shifted = np.roll(f, -90, axis=1)[::-1, :]  # starts at -180, rows south to north
    out = decode_grib_bytes(
        _raw_message(shifted, lon_first=-180.0, lon_last=178.0, j_positive=True)
    )
    assert out.grid == g
    assert np.abs(out.values - f).max() < 1e-5


def test_decoder_rejects_non_accumulated_fields():
    g = global_grid(2.0)
    with pytest.raises(GribError, match="accumulated"):
        decode_grib_bytes(
            _raw_message(
                _field(g), lon_first=0.0, lon_last=358.0, j_positive=False, step_type="instant"
            )
        )


def test_decoder_rejects_other_parameters_units():
    g = global_grid(2.0)
    with pytest.raises(GribError, match="units"):
        decode_grib_bytes(  # paramId 130 is temperature (K)
            _raw_message(
                _field(g), lon_first=0.0, lon_last=358.0, j_positive=False, units_param=130
            )
        )


def test_synthetic_model_properties():
    g = global_grid(1.0)
    lat, lon = g.lats[:, None], g.lons[None, :]
    w = np.cos(np.radians(lat)) * np.ones_like(lon)
    india = (lat > 8) & (lat < 30) & (lon > 70) & (lon < 90)
    out = dict(SyntheticModel("ecmwf-ifs").accumulations(RUN, g, [24, 48, 168]))
    mm_day = out[168] * 1000 / 7
    assert 1.5 < np.average(mm_day, weights=w) < 4.5  # plausible global mean
    assert mm_day[india].mean() > 2 * np.average(mm_day, weights=w)  # monsoon region is wet
    assert (out[48] >= out[24]).all() and (out[168] >= out[48]).all()  # accumulates
    assert (out[24] * 1000 >= 1).mean() < 0.4  # sparse, not drizzle everywhere


def test_synthetic_sources_agree_loosely_and_differ_by_run():
    g = global_grid(1.0)
    ifs = dict(SyntheticModel("ecmwf-ifs").accumulations(RUN, g, [72]))[72]
    aifs = dict(SyntheticModel("ecmwf-aifs").accumulations(RUN, g, [72]))[72]
    assert 0.7 < np.corrcoef(ifs.ravel(), aifs.ravel())[0, 1] < 0.995  # similar but not equal
    later = dict(
        SyntheticModel("ecmwf-ifs").accumulations(datetime(2026, 11, 5, 12, tzinfo=UTC), g, [72])
    )[72]
    assert not np.allclose(ifs, later)
    again = dict(SyntheticModel("ecmwf-ifs").accumulations(RUN, g, [72]))[72]
    assert np.array_equal(ifs, again)  # deterministic
