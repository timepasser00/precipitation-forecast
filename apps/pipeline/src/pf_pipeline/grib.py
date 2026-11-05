"""Decode (and, for tests and synthetic data, write) GRIB2 total-precipitation messages.

The decoder is strict on purpose. It only accepts what our derivation assumes: a regular
lat/lon grid, ``tp`` accumulated from the start of the forecast, in metres (or kg m-2, which is
millimetres). Anything else raises ``GribError`` instead of silently producing wrong rainfall.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import eccodes
import numpy as np

from precip_core.grid import GridSpec

from .fields import Field

TO_METRES = {"m": 1.0, "kg m**-2": 1e-3, "mm": 1e-3}


class GribError(ValueError):
    pass


def _decode_message(gid) -> Field:
    get = lambda k: eccodes.codes_get(gid, k)  # noqa: E731
    if get("gridType") != "regular_ll":
        raise GribError(f"unsupported gridType {get('gridType')!r} (need regular_ll)")
    if get("jPointsAreConsecutive"):
        raise GribError("jPointsAreConsecutive is not supported")
    if get("stepType") != "accum" or get("startStep") != 0:
        raise GribError(
            f"tp must be accumulated from the forecast start (stepType={get('stepType')!r}, "
            f"startStep={get('startStep')})"
        )
    if get("stepUnits") != 1:
        raise GribError("step units must be hours")
    units = get("units")
    if units not in TO_METRES:
        raise GribError(f"unexpected tp units {units!r}")

    ni, nj = int(get("Ni")), int(get("Nj"))
    arr = eccodes.codes_get_values(gid).astype(np.float32).reshape(nj, ni)
    missing = arr >= 1e19
    missing_fraction = float(missing.mean())
    if missing.any():
        arr = np.where(missing, np.float32(0.0), arr)
    arr *= np.float32(TO_METRES[units])
    # Lossy packing stores values in steps of about range / 2**bits. Differences of two packed
    # accumulations can therefore be wrong by about the sum of their steps (see derive.py).
    bits = int(get("bitsPerValue"))
    valid = arr[~missing]
    span_m = float(valid.max() - valid.min()) if valid.size else 0.0
    packing_step_mm = span_m * 1000.0 / (2**bits - 1) if bits > 0 else 0.0

    lat_first, lon_first = (
        get("latitudeOfFirstGridPointInDegrees"),
        get("longitudeOfFirstGridPointInDegrees"),
    )
    lat_last, lon_last = (
        get("latitudeOfLastGridPointInDegrees"),
        get("longitudeOfLastGridPointInDegrees"),
    )
    dlat, dlon = abs(get("jDirectionIncrementInDegrees")), abs(get("iDirectionIncrementInDegrees"))
    if get("iScansNegatively"):
        arr, lon_first, lon_last = arr[:, ::-1], lon_last, lon_first
    if get("jScansPositively"):
        arr, lat_first, lat_last = arr[::-1, :], lat_last, lat_first

    wrap = abs(ni * dlon - 360.0) < 1e-6
    lon0 = lon_first % 360.0
    if wrap:
        shift = round(lon0 / dlon)
        if shift:
            arr = np.roll(arr, shift, axis=1)  # make column 0 the 0-degree meridian
        lon0 = 0.0
    grid = GridSpec(float(lat_first), float(lon0), float(dlat), float(dlon), nj, ni, wrap)

    date, time = int(get("dataDate")), int(get("dataTime"))
    run_time = datetime(
        date // 10000, date // 100 % 100, date % 100, time // 100, time % 100, tzinfo=UTC
    )
    return Field(
        step=int(get("endStep")),
        values=np.ascontiguousarray(arr),
        grid=grid,
        run_time=run_time,
        meta={
            "missing_fraction": missing_fraction,
            "units": units,
            "packing_step_mm": packing_step_mm,
        },
    )


def decode_grib_file(path: str | Path, short_name: str = "tp") -> Iterator[Field]:
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                if eccodes.codes_get(gid, "shortName") == short_name:
                    yield _decode_message(gid)
            finally:
                eccodes.codes_release(gid)


def decode_grib_bytes(data: bytes) -> Field:
    gid = eccodes.codes_new_from_message(data)
    try:
        return _decode_message(gid)
    finally:
        eccodes.codes_release(gid)


def write_grib_message(
    values_m: np.ndarray, grid: GridSpec, step: int, run_time: datetime, *, bits: int = 16
) -> bytes:
    """Make a GRIB2 ``tp`` message with the same key conventions as ECMWF open data."""
    if not grid.wrap_lon:
        raise ValueError("only global grids can be written")
    gid = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        s = lambda k, v: eccodes.codes_set(gid, k, v)  # noqa: E731
        s("Ni", grid.nx)
        s("Nj", grid.ny)
        s("latitudeOfFirstGridPointInDegrees", grid.lat0)
        s("latitudeOfLastGridPointInDegrees", grid.lat0 - (grid.ny - 1) * grid.dlat)
        s("longitudeOfFirstGridPointInDegrees", grid.lon0)
        s("longitudeOfLastGridPointInDegrees", grid.lon0 + (grid.nx - 1) * grid.dlon)
        s("iDirectionIncrementInDegrees", grid.dlon)
        s("jDirectionIncrementInDegrees", grid.dlat)
        s("paramId", 228)  # tp, total precipitation, metres
        s("dataDate", int(run_time.strftime("%Y%m%d")))
        s("dataTime", run_time.hour * 100 + run_time.minute)
        s("stepType", "accum")
        s("startStep", 0)
        s("endStep", step)
        s("bitsPerValue", bits)
        eccodes.codes_set_values(gid, values_m.astype(np.float64).ravel())
        return eccodes.codes_get_message(gid)
    finally:
        eccodes.codes_release(gid)
