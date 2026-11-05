"""Tile format spike (ADR 0008): measure error and size of candidate encodings.

Usage (from the repo root):

    uv run python scripts/spike_tile_format.py                      # synthetic data, no network
    uv run python scripts/spike_tile_format.py --real --access aws  # real ECMWF data (needs network)
    uv run python scripts/spike_tile_format.py --grib data/raw/sample/ifs_0p25_tp.grib2
        # real fields from a local file (e.g. from `make sample`); only tiers at that resolution

It prints a markdown report. Synthetic fields compress differently from real ones, so rerun
with --real before trusting the sizes.
"""

from __future__ import annotations

import argparse
import io
import statistics
import time
import zlib
from datetime import UTC, datetime

import numpy as np
from PIL import Image

from pf_pipeline.adapters import make_adapter
from pf_pipeline.build import build_tier
from pf_pipeline.derive import plan_windows, required_steps, windows_to_mm
from pf_pipeline.grib import decode_grib_file
from pf_pipeline.runner import to_tier_grid
from precip_core.codec import dequantize, quantize
from precip_core.grid import res_from_code
from precip_core.manifest import TileConfig
from precip_core.registry import load_registry
from precip_core.tiling import BilinearSampler, tile_axes, tiles_for_bbox


def frames_from_grib(path, tier):
    """Frames from a local GRIB file: windows between whichever accumulated steps it holds."""
    acc, grid, noise = {}, None, {}
    for f in decode_grib_file(path):
        acc[f.step], grid = to_tier_grid(f, tier, res_from_code(tier.source_resolution))
        noise[f.step] = f.meta["packing_step_mm"]
    windows = plan_windows(set(acc), tier.fine_step_h, tier.fine_until_h, tier.daily_until_h)
    mm, _ = windows_to_mm(acc, windows, noise)
    return mm, grid, windows


def frames_for(reg, spec, tier, run_time, synthetic, access, grib=None):
    if grib:
        return frames_from_grib(grib, tier)
    steps = set(spec.steps_for(run_time))
    windows = plan_windows(steps, tier.fine_step_h, tier.fine_until_h, tier.daily_until_h)
    need = required_steps(windows)
    kwargs = {} if synthetic else ({"access": access} if access else {})
    adapter = make_adapter(
        spec, synthetic=synthetic, **({"as_grib": False} if synthetic else kwargs)
    )
    acc, grid, noise = {}, None, {}
    for f in adapter.iter_fields(run_time, tier.source_resolution, sorted(need)):
        acc[f.step], grid = to_tier_grid(f, tier, res_from_code(tier.source_resolution))
        noise[f.step] = f.meta.get("packing_step_mm", 0.0)
    mm, _ = windows_to_mm(acc, windows, noise)
    return mm, grid, windows


def png_size(arr, fmt="PNG"):
    buf = io.BytesIO()
    kw = (
        {"optimize": True, "compress_level": 9}
        if fmt == "PNG"
        else {"lossless": True, "quality": 100}
    )
    Image.fromarray(arr).save(buf, format=fmt, **kw)
    return buf.tell()


def sample_tiles(tier, grid, mm, size):
    z = tier.zoom_max
    out = []
    for x, y in tiles_for_bbox(z, tier.bbox):
        lon, lat = tile_axes(z, x, y, size)
        s = BilinearSampler(grid, lon, lat).apply(mm)
        west, south, east, north = tier.bbox
        box = ((lon >= west) & (lon <= east))[None, :] & ((lat >= south) & (lat <= north))[:, None]
        s = np.where(box, s, np.nan)
        if not np.isnan(s[0]).all():
            out.append(s)
    return out


def report_tier(reg, spec, tier, run_time, synthetic, access, grib=None):
    t0 = time.monotonic()
    mm, grid, _windows = frames_for(reg, spec, tier, run_time, synthetic, access, grib)
    enc, size = reg.encoding, reg.tile.size
    print(
        f"\n### {spec.id} / {tier.id}  ({mm.shape[0]} frames, grid {grid.ny}x{grid.nx}, "
        f"{tier.resolution_deg} deg; fetched+derived in {time.monotonic() - t0:.0f}s)\n"
    )
    wet = mm[mm >= enc.v0]
    print(
        f"wet cells (>= {enc.v0} mm): {wet.size / mm.size:.1%}; max {mm.max():.0f} mm; "
        f"p99 of wet {np.percentile(wet, 99):.1f} mm\n"
    )

    # 1. Quantisation error of the log8 scheme
    back = dequantize(quantize(mm, enc), enc)
    m = mm >= enc.v0
    rel = np.abs(back[m] - mm[m]) / mm[m]
    print("**Quantisation (log8, 1 byte/value)**\n")
    print(
        f"- relative error above {enc.v0} mm: median {np.median(rel):.2%}, p99 {np.percentile(rel, 99):.2%}, max {rel.max():.2%}"
    )
    print(f"- absolute error below {enc.v0} mm: max {np.abs(back[~m] - mm[~m]).max():.4f} mm")
    lin = np.rint(np.clip(mm, 0, 100) / 100 * 254)  # 8-bit linear to 100 mm, for contrast
    lin_back = lin / 254 * 100
    wet_small = (mm >= 0.1) & (mm < 1.0)
    print(
        f"- for contrast, linear 8-bit (0-100 mm): wipes out {np.mean(lin_back[wet_small] == 0):.0%} of 0.1-1 mm cells\n"
    )

    # 2. Encodings on identical sampled tiles
    tiles = sample_tiles(tier, grid, mm, size)
    q_tiles = [quantize(t, enc) for t in tiles]
    n = len(tiles)

    def row(name, total):
        per_tile = total / n / 1024
        return print(
            f"| {name} | {per_tile:,.0f} KB | {per_tile / mm.shape[0]:,.1f} KB | {total / 1024:,.0f} KB |"
        )

    print(
        f"**Encodings** ({n} tiles at zoom {tier.zoom_max}, all {mm.shape[0]} frames, one atlas per tile)\n"
    )
    print("| encoding | per tile | per tile per frame | all tiles |\n|---|---|---|---|")
    row("log8 PNG atlas (proposed)", sum(png_size(_atlas(q, 4)) for q in q_tiles))
    row("log8 WebP lossless atlas", sum(png_size(_atlas(q, 4), "WEBP") for q in q_tiles))
    lin_tiles = [
        np.where(np.isnan(t), 255, np.rint(np.clip(t, 0, 100) / 100 * 254)).astype(np.uint8)
        for t in tiles
    ]
    row("linear8 PNG atlas", sum(png_size(_atlas(q, 4)) for q in lin_tiles))
    pal = [
        np.where(np.isnan(t), 255, np.digitize(t, [0.1, 0.5, 1, 2, 5, 10, 20, 50, 100])).astype(
            np.uint8
        )
        for t in tiles
    ]
    row(
        "pre-coloured 10-level palette PNG (no GPU maths)", sum(png_size(_atlas(q, 4)) for q in pal)
    )

    # 3. Object size vs chunk length
    print("\n**Time frames per tile object** (log8 PNG)\n")
    print("| frames/object | objects per run | median | max | total |\n|---|---|---|---|---|")
    for fpc, cols in [(4, 2), (8, 4), (16, 4), (24, 6)]:
        art = build_tier(
            tier, grid, mm, TileConfig(size=size, frames_per_chunk=fpc, atlas_cols=cols), enc
        )
        sizes = [len(v) for k, v in art.objects.items() if k.endswith(".png")]
        print(
            f"| {fpc} | {len(sizes)} | {statistics.median(sizes) / 1024:,.0f} KB | {max(sizes) / 1024:,.0f} KB | {sum(sizes) / 1024:,.0f} KB |"
        )

    # 4. Cube layout
    q = quantize(mm, enc)
    cell_major = np.ascontiguousarray(np.transpose(q, (1, 2, 0))).tobytes()
    frame_major = np.ascontiguousarray(q).tobytes()
    print("\n**Point cube layout** (zlib level 9)\n")
    print(
        f"- raw {len(cell_major) / 1024:,.0f} KB; cell-major {len(zlib.compress(cell_major, 9)) / 1024:,.0f} KB; "
        f"frame-major {len(zlib.compress(frame_major, 9)) / 1024:,.0f} KB"
    )


def _atlas(q, cols):
    h, w = q.shape[1:]
    rows = -(-len(q) // cols)
    canvas = np.full((rows * h, cols * w), 255, dtype=np.uint8)
    for i, f in enumerate(q):
        r, c = divmod(i, cols)
        canvas[r * h : (r + 1) * h, c * w : (c + 1) * w] = f
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="use real ECMWF data (needs network)")
    ap.add_argument("--access", default=None)
    ap.add_argument("--grib", default=None, help="local GRIB file with tp fields (no network)")
    ap.add_argument("--source", default="ecmwf-ifs")
    ap.add_argument("--tiers", default="t0-global,t1-south-asia,t2-india")
    ap.add_argument("--run", default="2026110500")
    a = ap.parse_args()
    reg = load_registry()
    spec = reg.source(a.source)
    run_time = datetime.strptime(a.run, "%Y%m%d%H").replace(tzinfo=UTC)
    kind = "REAL (local GRIB)" if a.grib else "REAL" if a.real else "SYNTHETIC"
    print(f"## Tile format spike: {kind} data, run {a.run}")
    for t in reg.tiers_for(spec.id):
        if t.id not in a.tiers.split(","):
            continue
        if a.grib and t.source_resolution != "0p25":
            print(f"\n(skipping {t.id}: the file is 0p25 but the tier needs {t.source_resolution})")
            continue
        report_tier(reg, spec, t, run_time, not (a.real or a.grib), a.access, a.grib)


if __name__ == "__main__":
    main()
