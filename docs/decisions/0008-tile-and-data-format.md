# 0008: Tile and data format

Status: **accepted, provisional.** Measured on synthetic data (Phase 3 spike). Re-run `make sample`
then `make spike ARGS=--real` on real fields before Phase 4; section "What real data could change"
lists what would reopen this.

## Context
The browser must animate precipitation smoothly, switch palettes, and compute source-vs-source
differences. Request counts drive cost (ADR 0003, 0006). Browsers decode images to 8 bits per channel.

## Decision
- **Value-encoded raster tiles in Web Mercator (XYZ)**, not pre-coloured images. A pixel stores
  rainfall, not a colour; a WebGL shader maps values to colours, so palette changes, difference
  maps and crossfades between frames need no new downloads.
- **log8 quantisation.** One byte per value. `0` is 0 mm, `1..254` is log-spaced from 0.02 mm to
  1000 mm, `255` is no data. Relative error is at most 2.2% (median 1.1%) everywhere above 0.02 mm.
  Linear 8-bit over 0-100 mm would wipe out 20-23% of the 0.1-1 mm cells, which is most of what
  drizzle looks like, so it was rejected.
- **Atlas objects.** One lossless 8-bit grayscale PNG per (source, run, tier, tile, chunk),
  holding 8 frames in a 4-column grid. One request serves a block of the animation for that tile,
  and the first chunk can load first (lazy in time). Grayscale means no alpha channel, so there is
  no premultiplication to corrupt packed values.
- **Point cube, separate from tiles.** One object per (source, run, tier) with the native grid
  quantised the same way, laid out frame-major and zlib-compressed. The API samples it for point
  forecasts. Tiles are resampled to 256 px Mercator (oversampled at coarse zoom), so reading point
  values back out of them would add resampling error.
- **Manifest** (`manifest.json`) lists sources, runs, tiers, frames and object path templates.
  It is the only mutable object. See `docs/data-format.md`.

## Measurements (synthetic, 2026-11-06)
Production tiers and registry, run `2026110500`. Synthetic fields are smoother than real ones, so
treat sizes as a lower bound.

| Tier | Frames | Bytes (IFS) | Objects | Largest tile atlas (8 frames) |
|---|---|---|---|---|
| t0-global 0.5 deg | 36 | 10.3 MB | 106 | 136 KB |
| t1-south-asia 0.25 deg | 60 | 1.5 MB | 17 | - |
| t2-india 0.1 deg | 48 | 4.3 MB | 37 | 210 KB |

AIFS: t0 9.6 MB, t1 1.0 MB. Both sources, all tiers, one run: **26.8 MB** (two kept runs about
54 MB). Whole pipeline for both sources: 30 s wall, 525 MB peak memory (synthetic fetch, so real
download time is extra). Point cube: frame-major was 18-29% smaller than cell-major
(t0 2.5 MB vs 3.5 MB; t2 2.0 MB vs 2.3 MB), and since the body is one zlib stream cell-major gave
no random-access benefit, so frame-major is what the codec writes (the sizes in the table above
were taken before this change and include the larger cell-major cubes).

Frames per object, t0: 4 -> 189 objects, 8 -> 105, 16 -> 63, 24 -> 42; total bytes are flat
(about 6.4 MB). Median object at 8 frames is 60 KB on t0, which is small enough to cache well and
large enough to keep request counts low. 8 is kept; it is a registry setting.

Alternatives measured on the same tiles:

| Encoding | t0 all tiles | Verdict |
|---|---|---|
| log8 PNG atlas | 4.4 MB | **chosen** |
| log8 WebP lossless | 3.4 MB (-24%), t2 only -4% | revisit with real data and phone decode timing |
| linear8 PNG | 2.0 MB | rejected: loses drizzle |
| pre-coloured 10-level PNG | 0.9 MB | rejected: no palette switching, no client differences |

## What real data could change
1. Real fields are noisier, so PNG atlases will be larger; if objects exceed ~1 MB, lower
   `frames_per_chunk` to 4.
2. If WebP lossless keeps a >20% win on real data and decodes fast on mid-range phones, switch.
3. If `tp` is not accumulated from the forecast start in metres, derivation changes (the pipeline
   refuses to publish rather than guess; see `ConventionError`).

## Still open (Phase 4)
Decode speed on a mid-range phone; Cloudflare cache behaviour for these objects (ADR 0006);
fit with the custom WebGL layer (ADR 0009).

## Fallbacks
Custom binary with per-frame compression; Zarr chunks if range requests cache well; pre-coloured
tiles as the simplest fallback.

## Consequences
The codec is shared between pipeline (encode) and API (decode), so it lives in
`packages/precip-core`.
