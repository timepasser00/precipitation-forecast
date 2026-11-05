# Precipitation Forecast

A web app that turns ECMWF Open Data precipitation forecasts (IFS and AIFS) into an engaging, explorable experience.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Project structure | **Done** |
| 2 | Framework selection | **Done, pending review** (ADRs 0004, 0007-0011) |
| 3 | `git init` + backend API + docs | **Built, pending review** (real fields checked; one full real run outstanding) |
| 4 | Frontend UI | Not started |
| 5 | Optimization and scaling | Not started |

## Layout

```
apps/
  pipeline/        Fetch ECMWF GRIB2 -> decode -> derive -> write processed data   (batch, scheduled)
  api/             Read processed data -> serve forecasts over HTTP                (long-running, read-mostly)
  web/             Browser UI, talks only to the API                               (static/SSR frontend)
packages/
  precip-core/     Shared Python: grid, codec, manifest, storage, source registry
  api-contract/    Generated OpenAPI spec: the single source of truth between api and web
config/            sources.yaml: source and tier registry
infra/             Containers, deploy config, CI helpers
scripts/           Dev/ops helper scripts
data/              Local data (gitignored): raw/ GRIB2 downloads, processed/ derived output
docs/              Architecture, structure rules, data-source notes, decision records
```

## Quickstart (needs [uv](https://docs.astral.sh/uv/))

```
make setup     # install Python dependencies
make check     # lint + tests + OpenAPI drift check (what CI runs)
make synth     # publish synthetic demo data (no network needed)
make api       # API + interactive docs at http://localhost:8000/docs
make sample    # download a small real ECMWF sample and verify our assumptions (needs network)
```

Start with **`docs/DESIGN.md`**: the guiding document (goals, principles, tiers, cost guardrails, phases).
Then `docs/STRUCTURE.md` (boundaries), `docs/architecture.md` (data flow), `docs/data-format.md` and `docs/api.md`. Decisions are logged in `docs/decisions/`.
