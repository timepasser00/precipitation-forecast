# Repository structure and boundaries

## Why it is split this way

The system has three jobs with very different shapes. Each gets its own top-level app so it can use the right tools, be tested alone, and be scaled or deployed independently later (Phase 5).

| App | Job | Runtime shape | Why separate |
|---|---|---|---|
| `apps/pipeline` | Download and process forecast files | Batch, runs when new ECMWF runs land (00/06/12/18 UTC) | Heavy CPU/memory, scientific libraries, must not share a process with request serving |
| `apps/api` | Serve processed forecasts | Always-on, low latency | Scales with traffic, not with data volume |
| `apps/web` | Present the forecast | Browser | Different language/tooling and release cadence |

## Dependency rules (the part that keeps the split clean)

1. `web` talks to `api` over HTTP only, using types derived from `packages/api-contract`.
2. `api` never imports pipeline code. `pipeline` never imports api code.
3. `pipeline` and `api` meet at one place: the **processed data format** in `data/processed/` (later object storage). That format is documented in `docs/data-format.md` and is the only coupling between them. Storage is a directory in development and Cloudflare R2 in production (same interface).
4. Anything shared between apps lives in `packages/`. If two apps need the same code, it moves there. No reaching across `apps/*` directories. The first shared package is `packages/precip-core` (Python): source registry, manifest, storage and the codec used by both pipeline and api.
5. `data/` is never committed. Only the `.gitkeep` placeholders are.

## Where things go

- New endpoint: implement in `apps/api`, run `make openapi` to regenerate `packages/api-contract/openapi.json` (CI fails if it is stale), then consume it in `apps/web`.
- New derived field (e.g. a new accumulation window): `apps/pipeline`, then document in `docs/data-format.md`, then expose via the API.
- Deploy and container files: `infra/`. Each app keeps its own build config inside its own folder.
- Architecture decisions: one short file in `docs/decisions/` per decision, numbered.

## Stack

Languages, frameworks and tooling were chosen in Phase 2 (ADRs 0004, 0007-0011). The Python parts form one uv workspace (`pyproject.toml` at the root: `packages/precip-core`, `apps/pipeline`, `apps/api`). `config/sources.yaml` is the source and tier registry. `scripts/` holds helper scripts and `Makefile` the common tasks (`make help`).
