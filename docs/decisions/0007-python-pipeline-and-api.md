# 0007: Python for the pipeline and API

Status: accepted (2026-11-06)

## Context
The pipeline reads GRIB2 and does numeric work. The API is thin: it serves a manifest, source metadata and point series, and must be documented.

## Decision
- **Language:** Python 3.12, with environments and dependencies managed by `uv`.
- **Fetch:** the `ecmwf-opendata` client (ECMWF's own package; it can select the ECMWF, AWS, Azure or Google access path).
- **Decode:** `eccodes` with NumPy, called directly in the pipeline. `xarray` + `cfgrib` stay available for exploration and notebooks, not the hot path.
- **Encode:** Pillow and NumPy for tile output (see ADR 0008).
- **API:** FastAPI, Pydantic v2, uvicorn. Object storage access through the S3 API (boto3 as the default, **Proposed**).
- **Contract:** FastAPI generates the OpenAPI spec. The spec is exported to `packages/api-contract/openapi.json`, committed, and CI fails if it drifts from the code. The Angular client is generated from that file. Models and spec are reviewed before endpoint logic is written.

## Evidence (checked 2026-11-06)
- PyPI: ecmwf-opendata 0.3.35, eccodes 2.50.0, cfgrib 0.9.15.1, xarray 2026.9.0, numpy 2.5.4, fastapi 0.162.0, pydantic 2.14.3.
- Binary wheels resolve for macOS arm64, macOS x86_64, Linux x86_64 and Linux aarch64 (Python 3.12), so no compiler or system library install is needed.
- Smoke test on Python 3.12.3: wrote a synthetic global 0.25° GRIB2 field, decoded it with eccodes (max error 3.8e-06 at 12 bits per value) and with cfgrib/xarray. The file was 1.56 MB against 4.15 MB of raw float32.

## Alternatives considered
- **TypeScript everywhere:** one language with Angular, but GRIB tooling in JavaScript is weak. This is decisive for the pipeline.
- **Go or Rust:** fast, but the GRIB and scientific ecosystem is thinner and the cost for a solo developer is higher.
- **Django or Flask for the API:** heavier or less typed, and no automatic OpenAPI.
- **Litestar:** good, smaller community. FastAPI wins on documentation and examples.
- **API as a Cloudflare Worker:** cheap and near users, but splits the language stack. Revisit in Phase 5 if API cost or latency matters.
- **xarray/cfgrib in the pipeline hot path:** convenient, but more memory and overhead than needed for a few fields. Revisit if it proves simpler for non-ECMWF sources.

## Consequences
One language for data and API, so a shared Python package can hold the source registry models and tile codec (see STRUCTURE.md). The frontend consumes a generated client rather than hand-written types.
