# 0008: Tile and data format

Status: proposed, to be validated by a Phase 3 spike

## Context
The browser must animate precipitation smoothly, switch palettes, and compute IFS-vs-AIFS differences. Request counts drive cost (ADR 0003, 0006). Browsers decode images to 8 bits per channel.

## Proposal
- **Value-encoded raster tiles in Web Mercator (XYZ)**, not pre-coloured images. Each pixel stores precipitation, not a colour. A WebGL shader maps values to colours, so palette, difference maps and crossfades between time steps happen on the GPU without new downloads.
- **Time-stacked objects.** One object per (source, run, tier, tile, time-chunk), a lossless PNG atlas holding several time steps side by side. One request serves a block of the animation for that tile, which cuts request count and makes scrubbing instant. Time-chunking also gives lazy loading in time (first chunk first).
- **Encoding.** Non-linear 8-bit or two-channel 16-bit packing, always with alpha fixed at 255. With alpha below 255, browser canvas decoding premultiplies colour and corrupts packed values.
- **Point series** come from the same tiles (decoded server-side by the API, or read directly in the browser), not a separate store.
- **Manifest** (JSON) lists sources, runs, tiers, steps and object locations.

## Spike questions (Phase 3)
1. Quantisation error vs file size on real IFS and AIFS fields.
2. Object sizes and request counts per run (target: medium objects, hundreds of KB to a few MB).
3. Decode speed on a mid-range phone.
4. Cloudflare cache behaviour for these objects (ADR 0006).
5. Whether the atlas layout works well with the custom WebGL layer (ADR 0009).

## Fallbacks
- Custom binary with per-step compression decoded in the browser.
- Zarr chunks, if range requests turn out to cache well.
- Pre-coloured PNG tiles: simplest, but no palette switching and no client-side differences.

## Consequences
The tile codec is shared between pipeline (encode) and API (decode), so it lives in a shared Python package.
