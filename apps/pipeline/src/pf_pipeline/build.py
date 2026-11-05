"""Turn per-frame rainfall grids into the objects we publish: tile atlases and a point cube."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from precip_core.codec import Encoding, encode_atlas, encode_cube, quantize
from precip_core.grid import GridSpec
from precip_core.manifest import TileConfig
from precip_core.registry import TierSpec
from precip_core.tiling import BilinearSampler, tile_axes, tiles_for_bbox


@dataclass
class TierArtifacts:
    objects: dict[str, bytes]  # key relative to the tier directory
    tiles: dict[int, list[tuple[int, int]]]
    grid: GridSpec
    chunks: int

    @property
    def total_bytes(self) -> int:
        return sum(len(v) for v in self.objects.values())


def build_tier(
    tier: TierSpec, grid: GridSpec, frames_mm: np.ndarray, cfg: TileConfig, enc: Encoding
) -> TierArtifacts:
    """``frames_mm`` has shape (frames, ny, nx) on ``grid``."""
    n_frames = frames_mm.shape[0]
    chunks = math.ceil(n_frames / cfg.frames_per_chunk)
    west, south, east, north = tier.bbox
    objects: dict[str, bytes] = {}
    tiles: dict[int, list[tuple[int, int]]] = {}

    for z in range(tier.zoom_min, tier.zoom_max + 1):
        tiles[z] = []
        for x, y in tiles_for_bbox(z, tier.bbox):
            lon, lat = tile_axes(z, x, y, cfg.size)
            sampled = BilinearSampler(grid, lon, lat).apply(frames_mm)  # (F, size, size)
            in_box = ((lon >= west) & (lon <= east))[None, :] & ((lat >= south) & (lat <= north))[
                :, None
            ]
            sampled = np.where(in_box, sampled, np.float32(np.nan))
            if np.isnan(sampled[0]).all():
                continue  # tile lies outside what this tier covers
            q = quantize(sampled, enc)
            tiles[z].append((x, y))
            for c in range(chunks):
                lo, hi = c * cfg.frames_per_chunk, min(n_frames, (c + 1) * cfg.frames_per_chunk)
                objects[f"{z}/{x}/{y}/c{c}.png"] = encode_atlas(list(q[lo:hi]), cfg.atlas_cols)

    cube_q = np.transpose(quantize(frames_mm, enc), (1, 2, 0))
    header = {"grid": grid.to_dict(), "encoding": enc.model_dump(), "frames": n_frames}
    objects["cube.pfc"] = encode_cube(cube_q, header)
    return TierArtifacts(objects=objects, tiles=tiles, grid=grid, chunks=chunks)
