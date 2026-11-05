# Processed data format

The only coupling between `apps/pipeline` (writes) and `apps/api` / `apps/web` (read). The code
that defines it is `packages/precip-core`. Schema version: **1**.

## Layout in object storage

```
manifest.json                                                     mutable, 60 s cache
runs/{source}/{YYYYMMDDHH}/{tier}/{z}/{x}/{y}/c{chunk}.png        immutable, 1 year
runs/{source}/{YYYYMMDDHH}/{tier}/cube.pfc                        immutable, 1 year
```

`source` is a registry id such as `ecmwf-ifs`. `YYYYMMDDHH` is the model run start in UTC.
Everything except the manifest is write-once: a published object never changes, which is why it
can be cached for a year. New data means new keys.

## Publish protocol (why readers never see half a run)
1. Upload every object of a tier under its run prefix.
2. Only then update the manifest (one small atomic write) to point at it.
3. Prune runs older than the newest two complete ones, after the manifest no longer lists them.

A crash between 1 and 2 leaves orphan objects and an unchanged manifest. Rerunning the same run
overwrites them with identical content (the pipeline is idempotent). The pipeline refuses to mix
synthetic and real runs in one store.

## Values
Rainfall in millimetres per frame window, one byte per value (log8):

| Code | Meaning |
|---|---|
| 0 | 0 mm |
| 1..254 | `0.02 * exp((q - 1) / 253 * ln(1000 / 0.02))` mm |
| 255 | no data (outside the tier's area) |

Relative error above 0.02 mm is at most 2.2%. The constants are in the manifest (`encoding`) so
clients never hard-code them.

## Frames
A frame is one time window `[start, end)` in UTC: either an `interval` (3 or 6 h, fine part of the
forecast) or a `daily` 24 h total (further out). Rainfall over a window is `tp(end) - tp(start)`,
clipped at 0. Frame lists are per tier in the manifest.

## Tile atlas (`c{chunk}.png`)
- 8-bit grayscale PNG, Web Mercator XYZ tile, 256 px tile size (from `tile.size`).
- Holds up to `tile.frames_per_chunk` (8) frames in a grid with `tile.atlas_cols` (4) columns,
  frame `i` at row `i // cols`, column `i % cols`, row-major.
- Chunk `c` holds frames `c*8 .. c*8+7` of the tier's frame list. The last chunk may be partial.
- Only tiles that intersect the tier's bbox exist; the manifest lists them in `tiles[zoom]`.
  Pixels inside an existing tile but outside the bbox are 255.

## Point cube (`cube.pfc`)
```
bytes 0-3   magic "PFC1"
bytes 4-7   uint32 little-endian: header length N
bytes 8..   JSON header of N bytes: grid, encoding, frames, shape [ny, nx, frames],
            layout "frame-major", compression "zlib"
rest        zlib stream of uint8 values, frame-major: index = (frame * ny + row) * nx + col
```
The native tier grid, quantised as above. Rows run north to south, columns west to east,
longitudes in degrees east from the grid's `lon0`. Used server-side for point forecasts.

## Manifest (`manifest.json`)
```
schema_version, generated_at, encoding{...}, tile{size, crs, frames_per_chunk, atlas_cols}
sources: { <id>: { latest, previous, runs: { <YYYYMMDDHH>: {
    run_time, status: partial|complete, synthetic, published_at,
    tiers: { <tier>: { id, name, resolution_deg, bbox, zoom_min, zoom_max, grid,
                       frames[{start,end,start_h,end_h,kind}], chunks,
                       tiles{zoom: [[x,y],...]}, tile_path, cube_path, bytes } } } } } }
```
`latest` and `previous` name the two newest runs that have every required tier. `tile_path` is a
template with `{z} {x} {y} {chunk}`. Clients must treat a missing tier as "not available for this
run", not as an error, because optional tiers (for example `t2-india`) may be absent.

## Changing the format
Bump `schema_version`, keep readers tolerant of unknown fields, and add an ADR. Old runs age out
within two runs, so there is no long-term migration burden.
