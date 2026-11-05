"""Point sampling from a decoded cube: bilinear in space, one value per frame."""

from __future__ import annotations

import numpy as np

from precip_core.codec import Encoding, dequantize
from precip_core.grid import axis_weights, lat_frac, lon_frac

from .state import Cube


def sample_point(cube: Cube, lat: float, lon: float) -> np.ndarray | None:
    """Rainfall (mm) per frame at a location, or None if it lies outside the cube's grid.

    Only the four surrounding cells are decoded, so the cost does not depend on grid size.
    """
    g = cube.grid
    r0, r1, wy, in_y = axis_weights(lat_frac(g, np.array([lat])), g.ny, False)
    c0, c1, wx, in_x = axis_weights(lon_frac(g, np.array([lon])), g.nx, g.wrap_lon)
    if not (in_y[0] and in_x[0]):
        return None
    enc = Encoding(**cube.header["encoding"])
    a, b = dequantize(cube.q[r0[0], c0[0]], enc), dequantize(cube.q[r0[0], c1[0]], enc)
    c, d = dequantize(cube.q[r1[0], c0[0]], enc), dequantize(cube.q[r1[0], c1[0]], enc)
    x, y = float(wx[0]), float(wy[0])
    return (a * (1 - x) + b * x) * (1 - y) + (c * (1 - x) + d * x) * y
