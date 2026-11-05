# API guide

Read-only, versioned under `/v1`. The machine-readable contract is
[`packages/api-contract/openapi.json`](../packages/api-contract/openapi.json), generated from the
FastAPI app and checked in CI. Interactive docs are served by the running API at `/docs`
(Swagger UI) and `/redoc`.

Map tiles are **not** served by the API. Clients read `manifest.json` and fetch tiles from the CDN.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Liveness, and whether any run has been published |
| `GET /v1/config` | Where the data host is (`data_base_url`, `manifest_url`) |
| `GET /v1/manifest` | The manifest, as map clients read it from the CDN |
| `GET /v1/sources` | Sources with latest/previous run, tiers, licence attribution, `synthetic` flag |
| `GET /v1/point` | Rainfall per frame at a location, one source |
| `GET /v1/compare` | The same location across several sources |
| `GET /data/*` | Raw tiles and cubes. **Development only** (`PF_API_SERVE_DATA=true`) |

### `GET /v1/point?lat=19.07&lon=72.88&source=ecmwf-ifs`
Parameters: `lat` (-90..90), `lon` (-180..360, east), `source` (default `ecmwf-ifs`), `run`
(`YYYYMMDDHH`, default latest), `tier` (default: the finest tier covering the point).

```json
{
  "source": "ecmwf-ifs", "run": "2026110500", "run_time": "2026-11-05T00:00:00Z",
  "tier": "t2-india", "resolution_deg": 0.1, "lat": 19.07, "lon": 72.88, "units": "mm",
  "synthetic": false,
  "frames": [{"start": "2026-11-05T00:00:00Z", "end": "2026-11-05T03:00:00Z",
              "kind": "interval", "mm": 0.38}],
  "totals_mm": {"24h": 1.7, "48h": 6.6, "72h": 8.3, "120h": 28.0},
  "attribution": "..."
}
```
Values are bilinear from the four surrounding cells of the native grid, not from map tiles.
`totals_mm` only contains horizons fully covered by the tier's frames. `mm` is `null` where there
is no data.

### `GET /v1/compare?lat=28.6&lon=77.2&sources=ecmwf-ifs,ecmwf-aifs`
Latest run of each source (default: all published). Each result has the same shape as `/v1/point`,
and all use UTC frame boundaries so they can be overlaid. A source that cannot answer is listed in
`errors` and does not hide the others; 404 only if none can answer.

## Errors
`{"detail": "..."}` with: `404` unknown source/run/tier, nothing published yet, or the point lies
outside the area covered; `422` invalid parameters; `503` an object the manifest lists is missing
from storage (a pipeline/storage fault).

## Caching
| Response | `Cache-Control` |
|---|---|
| `/v1/point` with `run` given | `public, max-age=31536000, immutable` |
| `/v1/point`, `/v1/compare`, `/v1/sources`, `/v1/manifest` following latest | `public, max-age=60` |
| `/v1/config` | `public, max-age=300` |

Inside the process: the manifest is cached for 30 s, and the 6 most recently used decoded cubes
stay in memory (a cold point query on the 0.1 deg tier took about 28 ms, a warm one about 3 ms in
the Phase 3 smoke test).

## Configuration (environment, prefix `PF_API_`)
| Variable | Default | Meaning |
|---|---|---|
| `STORAGE_URL` | `data/processed/store` | Directory or `s3://bucket/prefix?endpoint_url=...` (R2) |
| `DATA_BASE_URL` | `/data` | Public prefix for tile/cube paths (the CDN in production) |
| `SERVE_DATA` | `false` | Serve `/data/*` from storage (development only) |
| `CONFIG_PATH` | `config/sources.yaml` | Registry, for source names and licences (optional) |
| `CORS_ORIGINS` | `["http://localhost:4200"]` | Allowed browser origins (JSON list) |
| `MANIFEST_TTL_S` / `CUBE_CACHE_SIZE` | `30` / `6` | In-process cache tuning |

## Run it
```
make synth    # publish synthetic demo data into data/processed/store
make api      # http://localhost:8000/docs
```
