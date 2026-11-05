# apps/pipeline

Batch job: fetch forecasts, decode GRIB2, derive per-window rainfall, build tiles and point
cubes, upload, then flip the manifest. Idempotent: rerunning a run is safe.

```
uv run pf-pipeline run --synthetic --run latest --storage data/processed/store   # demo data
uv run pf-pipeline run --source ecmwf-ifs --run latest --storage s3://bucket?endpoint_url=...
uv run pf-pipeline status --storage data/processed/store
uv run pf-pipeline inspect path/to/file.grib2     # what is in a GRIB file
uv run pf-pipeline sample                         # real-data check, needs network
```

Flow per source and run: `adapter.fetch` (ordered access paths, retries) -> `grib` (strict
decode, orientation normalised) -> `derive` (windows from accumulated tp) -> `runner.to_tier_grid`
-> `build` (atlases + cube) -> upload -> `_register_tier` (manifest flip, prune).

Safety rails: strict GRIB decoding (regular lat/lon, accumulated, hours, m or kg m-2),
`ConventionError` if rainfall decreases between steps, refusal to mix synthetic and real runs,
and tiers publish independently so a failed optional tier never blocks the rest.

Sources are adapters (`adapters/`): `ecmwf` (via `ecmwf-opendata`) and `synthetic`. A new source is
a registry entry in `config/sources.yaml` plus, if its format differs, a new adapter.

`make sample` writes `data/raw/sample/report.txt` listing the real GRIB keys and PASS/FAIL against
the assumptions the decoder makes. Run it first on any new machine or after an ECMWF change.

Needs the ecCodes library, installed as a wheel (`eccodeslib`; macOS 15+ on Apple silicon/Intel).
