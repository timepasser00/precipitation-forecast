# 0010: Tooling, conventions and CI

Status: accepted as baseline (2026-11-06)

## Decision
- **Python:** `uv` for environments and workspaces, `ruff` for lint and format, `pytest` for tests, a type checker (mypy, **Proposed**).
- **Frontend:** `npm` with the Angular CLI defaults for build, lint and test (confirm the default test runner when scaffolding in Phase 4).
- **Task runner:** a root `Makefile` with a few targets (setup, test, lint, run). No extra tool to install.
- **CI:** GitHub Actions, if the repo is hosted on GitHub (**Proposed**; owner to confirm). Jobs: lint and test per app, OpenAPI drift check, cache-header check against a staging bucket (ADR 0006).
- **Shared code:** `packages/precip-core` (Python), created in Phase 3, holds source registry models and the tile codec used by both pipeline and API.
- **Commits:** small, one logical change each, with a clear message.

## Alternatives considered
- **pnpm or Nx/Turborepo:** not needed for one frontend app.
- **just/Taskfile:** nicer syntax, but another install for a few commands.
- **pre-commit hooks:** deferred until the team is larger than one.

## Consequences
Minimal tooling to learn and maintain. Revisit when a second contributor joins.
