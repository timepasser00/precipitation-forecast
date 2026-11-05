# Precipitation Forecast

A web app that turns ECMWF Open Data precipitation forecasts (IFS and AIFS) into an engaging, explorable experience.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Project structure | **Done** |
| 2 | Framework selection | In progress (Angular chosen) |
| 3 | `git init` + backend API + docs | Not started |
| 4 | Frontend UI | Not started |
| 5 | Optimization and scaling | Not started |

## Layout

```
apps/
  pipeline/        Fetch ECMWF GRIB2 -> decode -> derive -> write processed data   (batch, scheduled)
  api/             Read processed data -> serve forecasts over HTTP                (long-running, read-mostly)
  web/             Browser UI, talks only to the API                               (static/SSR frontend)
packages/
  api-contract/    OpenAPI spec: the single source of truth between api and web
infra/             Containers, deploy config, CI helpers
scripts/           Dev/ops helper scripts
data/              Local data (gitignored): raw/ GRIB2 downloads, processed/ derived output
docs/              Architecture, structure rules, data-source notes, decision records
```

Start with **`docs/DESIGN.md`**: the guiding document (goals, principles, tiers, cost guardrails, phases).
Then `docs/STRUCTURE.md` (boundaries) and `docs/architecture.md` (data flow). Decisions are logged in `docs/decisions/`.
