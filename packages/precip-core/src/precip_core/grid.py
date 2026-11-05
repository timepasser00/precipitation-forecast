"""Regular latitude/longitude grids.

Convention used everywhere in this project:
  * rows run north to south (``lat0`` is the northernmost row, ``dlat`` is positive),
  * columns run west to east, with longitudes in degrees east in [0, 360),
  * a global grid wraps in longitude (``wrap_lon=True``).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

BBox = tuple[float, float, float, float]  # west, south, east, north (degrees, lon -180..180)
GLOBAL_BBOX: BBox = (-180.0, -90.0, 180.0, 90.0)


def res_from_code(code: str) -> float:
    """ECMWF-style resolution code to degrees: '0p25' -> 0.25, '0p1' -> 0.1."""
    return float(code.replace("p", "."))


@dataclass(frozen=True)
class GridSpec:
    lat0: float
    lon0: float
    dlat: float
    dlon: float
    ny: int
    nx: int
    wrap_lon: bool = False

    @property
    def shape(self) -> tuple[int, int]:
        return (self.ny, self.nx)

    @property
    def lats(self) -> np.ndarray:
        return self.lat0 - np.arange(self.ny) * self.dlat

    @property
    def lons(self) -> np.ndarray:
        return self.lon0 + np.arange(self.nx) * self.dlon

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> GridSpec:
        return cls(**d)


def global_grid(res: float) -> GridSpec:
    """Global grid including both poles, longitudes 0..360-res."""
    ny = round(180.0 / res) + 1
    nx = round(360.0 / res)
    return GridSpec(90.0, 0.0, res, res, ny, nx, wrap_lon=True)


def is_global(bbox: BBox) -> bool:
    return bbox[0] <= -180.0 and bbox[2] >= 180.0 and bbox[1] <= -90.0 and bbox[3] >= 90.0


def crop_grid(grid: GridSpec, bbox: BBox, margin: int = 1) -> tuple[GridSpec, slice, slice]:
    """Crop to a bounding box plus ``margin`` cells (so bilinear sampling works at the edge)."""
    if is_global(bbox):
        return grid, slice(None), slice(None)
    west, south, east, north = bbox
    w = west % 360.0
    e = 360.0 if east == 360.0 else east % 360.0
    if e < w:
        raise ValueError("bbox crossing the prime meridian is not supported")
    eps = 1e-9
    r0 = max(0, math.ceil((grid.lat0 - north) / grid.dlat - eps) - margin)
    r1 = min(grid.ny, math.floor((grid.lat0 - south) / grid.dlat + eps) + 1 + margin)
    c0 = max(0, math.ceil((w - grid.lon0) / grid.dlon - eps) - margin)
    c1 = min(grid.nx, math.floor((e - grid.lon0) / grid.dlon + eps) + 1 + margin)
    sub = GridSpec(
        lat0=grid.lat0 - r0 * grid.dlat,
        lon0=grid.lon0 + c0 * grid.dlon,
        dlat=grid.dlat,
        dlon=grid.dlon,
        ny=r1 - r0,
        nx=c1 - c0,
        wrap_lon=False,
    )
    return sub, slice(r0, r1), slice(c0, c1)


def coarsen2(field: np.ndarray, grid: GridSpec) -> tuple[np.ndarray, GridSpec]:
    """Halve the resolution of a global grid (e.g. 0.25 to 0.5 degrees).

    A [1 2 1]/4 tent filter is applied before taking every second point, which keeps the
    area mean of rainfall approximately intact and avoids aliasing.
    """
    if not (grid.wrap_lon and grid.nx % 2 == 0 and (grid.ny - 1) % 2 == 0):
        raise ValueError("coarsen2 needs a global grid with an even number of columns")
    f = field.astype(np.float32, copy=False)
    f = 0.25 * np.roll(f, 1, axis=1) + 0.5 * f + 0.25 * np.roll(f, -1, axis=1)
    p = np.pad(f, ((1, 1), (0, 0)), mode="edge")
    f = 0.25 * p[:-2] + 0.5 * p[1:-1] + 0.25 * p[2:]
    f = np.ascontiguousarray(f[::2, ::2])
    out = GridSpec(grid.lat0, grid.lon0, grid.dlat * 2, grid.dlon * 2, f.shape[0], f.shape[1], True)
    return f, out


def axis_weights(frac: np.ndarray, n: int, wrap: bool):
    """Bilinear indices and weights along one axis.

    ``frac`` holds fractional index coordinates. Returns (i0, i1, w, inside) where the sample is
    ``(1 - w) * a[i0] + w * a[i1]`` and ``inside`` marks coordinates within the grid extent.
    """
    frac = np.asarray(frac, dtype=np.float64)
    if wrap:
        f0 = np.floor(frac)
        w = frac - f0
        i0 = f0.astype(np.int64) % n
        i1 = (i0 + 1) % n
        inside = np.ones(frac.shape, dtype=bool)
    else:
        inside = (frac >= 0) & (frac <= n - 1)
        fc = np.clip(frac, 0, n - 1)
        i0 = np.minimum(np.floor(fc).astype(np.int64), n - 2)
        w = fc - i0
        i1 = i0 + 1
    return i0, i1, w.astype(np.float32), inside


def lat_frac(grid: GridSpec, lat: np.ndarray) -> np.ndarray:
    return (grid.lat0 - np.asarray(lat, dtype=np.float64)) / grid.dlat


def lon_frac(grid: GridSpec, lon: np.ndarray) -> np.ndarray:
    return (np.mod(np.asarray(lon, dtype=np.float64), 360.0) - grid.lon0) / grid.dlon
