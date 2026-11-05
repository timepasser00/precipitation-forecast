"""Value encoding for tiles and point cubes.

Precipitation (millimetres) is stored as one unsigned byte per value on a logarithmic scale:

  q = 0        exactly zero (anything below ``v0``)
  q = 1..254   v0 * exp((q - 1) / 253 * ln(vmax / v0)), i.e. a constant relative step
  q = 255      no data (outside the area a tier covers)

With the defaults (v0 = 0.02 mm, vmax = 1000 mm) the relative error is at most about 2.2%
above v0, and the absolute error is below 0.02 mm under it. Tiles hold several time steps
side by side as a lossless 8-bit grayscale PNG ("atlas"), so browsers can decode them
natively and upload them straight to the GPU.
"""

from __future__ import annotations

import io
import json
import math
import struct
import zlib
from functools import lru_cache
from typing import Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel

STEPS = 253
NODATA = 255
CUBE_MAGIC = b"PFC1"


class Encoding(BaseModel, frozen=True):
    kind: Literal["log8"] = "log8"
    units: Literal["mm"] = "mm"
    v0: float = 0.02
    vmax: float = 1000.0
    zero: int = 0
    first_level: int = 1
    last_level: int = 254
    nodata: int = NODATA


@lru_cache(maxsize=8)
def _lut(v0: float, vmax: float) -> np.ndarray:
    ln_range = math.log(vmax / v0)
    lut = np.empty(256, dtype=np.float32)
    lut[0] = 0.0
    q = np.arange(1, 255)
    lut[1:255] = v0 * np.exp((q - 1) / STEPS * ln_range)
    lut[255] = np.nan
    return lut


def quantize(values: np.ndarray, enc: Encoding | None = None) -> np.ndarray:
    """Millimetres (NaN = no data) to uint8 codes."""
    enc = enc or Encoding()
    v = np.asarray(values, dtype=np.float32)
    q = np.zeros(v.shape, dtype=np.uint8)
    nodata = np.isnan(v)
    pos = (~nodata) & (v >= enc.v0)
    ln_range = math.log(enc.vmax / enc.v0)
    t = np.log(np.clip(v[pos], enc.v0, enc.vmax) / enc.v0) / ln_range
    q[pos] = (1 + np.rint(t * STEPS)).astype(np.uint8)
    q[nodata] = NODATA
    return q


def dequantize(q: np.ndarray, enc: Encoding | None = None) -> np.ndarray:
    """uint8 codes to millimetres (NaN = no data)."""
    enc = enc or Encoding()
    return _lut(enc.v0, enc.vmax)[q]


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def encode_atlas(frames: list[np.ndarray], cols: int) -> bytes:
    """Lay out equally sized uint8 frames left to right, top to bottom, as one PNG.

    Unused cells at the end are filled with NODATA.
    """
    h, w = frames[0].shape
    rows = math.ceil(len(frames) / cols)
    canvas = np.full((rows * h, cols * w), NODATA, dtype=np.uint8)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        canvas[r * h : (r + 1) * h, c * w : (c + 1) * w] = f
    return _png(canvas)


def decode_atlas(png: bytes, n_frames: int, cols: int, tile: int = 256) -> np.ndarray:
    """Inverse of :func:`encode_atlas`; returns (n_frames, tile, tile) uint8."""
    img = np.asarray(Image.open(io.BytesIO(png)))
    out = np.empty((n_frames, tile, tile), dtype=np.uint8)
    for i in range(n_frames):
        r, c = divmod(i, cols)
        out[i] = img[r * tile : (r + 1) * tile, c * tile : (c + 1) * tile]
    return out


def encode_cube(q: np.ndarray, header: dict) -> bytes:
    """Point-query cube: ``q`` has shape (ny, nx, frames) in memory.

    Bytes are stored frame-major (frames, ny, nx): spike measurements showed this compresses
    18-29% smaller than cell-major, and the whole body is one zlib stream so cell-major would
    give no random-access benefit anyway.

    Layout: magic 'PFC1' | uint32 header length | JSON header | zlib-compressed bytes.
    """
    if q.ndim != 3 or q.dtype != np.uint8:
        raise ValueError("cube must be a 3-D uint8 array (ny, nx, frames)")
    hdr = dict(header)
    hdr.update({"shape": list(q.shape), "layout": "frame-major", "compression": "zlib"})
    raw = json.dumps(hdr, sort_keys=True).encode()
    body = zlib.compress(np.ascontiguousarray(np.moveaxis(q, 2, 0)).tobytes(), 9)
    return CUBE_MAGIC + struct.pack("<I", len(raw)) + raw + body


def decode_cube(data: bytes) -> tuple[dict, np.ndarray]:
    if data[:4] != CUBE_MAGIC:
        raise ValueError("not a point cube (bad magic)")
    (n,) = struct.unpack("<I", data[4:8])
    header = json.loads(data[8 : 8 + n])
    ny, nx, nf = header["shape"]
    fm = np.frombuffer(zlib.decompress(data[8 + n :]), dtype=np.uint8).reshape(nf, ny, nx)
    return header, np.moveaxis(fm, 0, 2)
