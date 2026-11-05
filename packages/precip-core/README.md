# packages/precip-core

Shared Python library: the pieces the pipeline writes with and the API reads with.

| Module | Contents |
|---|---|
| `grid` | Regular lat/lon grid model (north to south rows, longitudes east), cropping, coarsening |
| `tiling` | Web Mercator tile math, bilinear resampling |
| `codec` | log8 quantisation, PNG atlases, point cube |
| `manifest` | Manifest models, pointer refresh, retention |
| `storage` | `LocalStorage`, `S3Storage` (works with Cloudflare R2) |
| `registry` | `config/sources.yaml` models |

Format reference: [`docs/data-format.md`](../../docs/data-format.md). Tests: `uv run pytest packages/precip-core`.
