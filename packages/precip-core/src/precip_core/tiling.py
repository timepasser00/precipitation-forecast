"""Web Mercator (XYZ) tile math and bilinear resampling of lat/lon grids onto tile pixels."""

from __future__ import annotations

import math

import numpy as np

from .grid import BBox, GridSpec, axis_weights, lat_frac, lon_frac

MAX_LAT = 85.0511287798


def tile_axes(z: int, x: int, y: int, size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """Longitudes (west to east) and latitudes (north to south) of tile pixel centres."""
    n = 2**z
    frac = (np.arange(size) + 0.5) / size
    lon = (x + frac) / n * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * (y + frac) / n))))
    return lon, lat


def _tile_y(lat: float, n: int) -> float:
    lat = max(min(lat, MAX_LAT), -MAX_LAT)
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n


def tiles_for_bbox(z: int, bbox: BBox) -> list[tuple[int, int]]:
    """All (x, y) tiles at zoom ``z`` that intersect the bbox."""
    west, south, east, north = bbox
    n = 2**z
    eps = 1e-9
    x0 = math.floor((west + 180.0) / 360.0 * n + eps)
    x1 = math.floor((east + 180.0) / 360.0 * n - eps)
    y0 = math.floor(_tile_y(north, n) + eps)
    y1 = math.floor(_tile_y(south, n) - eps)
    x0, x1 = max(0, x0), min(n - 1, max(x1, x0))
    y0, y1 = max(0, y0), min(n - 1, max(y1, y0))
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


class BilinearSampler:
    """Resample stacks of grids onto separable (lon, lat) axes. NaN outside the grid extent."""

    def __init__(self, grid: GridSpec, lon: np.ndarray, lat: np.ndarray):
        self.grid = grid
        self.r0, self.r1, self.wy, self.in_y = axis_weights(lat_frac(grid, lat), grid.ny, False)
        self.c0, self.c1, self.wx, self.in_x = axis_weights(
            lon_frac(grid, lon), grid.nx, grid.wrap_lon
        )

    @property
    def inside(self) -> np.ndarray:
        return self.in_y[:, None] & self.in_x[None, :]

    def apply(self, stack: np.ndarray) -> np.ndarray:
        """``stack`` has shape (..., ny, nx); result has shape (..., len(lat), len(lon))."""
        r0, r1 = self.r0[:, None], self.r1[:, None]
        c0, c1 = self.c0[None, :], self.c1[None, :]
        wy, wx = self.wy[:, None], self.wx[None, :]
        a, b = stack[..., r0, c0], stack[..., r0, c1]
        c, d = stack[..., r1, c0], stack[..., r1, c1]
        out = (a * (1 - wx) + b * wx) * (1 - wy) + (c * (1 - wx) + d * wx) * wy
        return np.where(self.inside, out, np.float32(np.nan)).astype(np.float32, copy=False)
