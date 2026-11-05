# 0003: Static-first delivery and cost guardrails

Status: accepted as baseline (2026-11-06)

## Context
Production is paid from personal funds. The main cost risks are egress, per-request compute, request-count billing and autoscaling, not storage.

## Decision
- Pipeline pre-builds all data. Serving is file reads from object storage behind a CDN.
- Immutable versioned paths with long cache lifetimes. One small mutable manifest with a short lifetime.
- The API is thin and read-only. Tiles do not pass through it.
- Pack tiles into few large objects.
- No autoscaling services. Billing alerts from day one.
- Target steady-state at or under $10 per month, alert at $15 (proposed).
- Storage accessed through an S3-compatible interface to keep provider choice open. Cloudflare R2 is the first candidate (free egress).

## Alternatives considered
- **Serve tiles from the application server:** simple, but egress and CPU would drive the bill.
- **Compute tiles per request (serverless or VM):** flexible, but cost and latency scale with traffic.
- **Managed autoscaling platform:** convenient, but cost is unbounded without strict caps.

## Consequences
Cost stays nearly flat as traffic grows, provided caching works, so cache headers become a tested requirement. Dynamic features need either to fit the thin API or to be precomputed. Prices must be re-verified before committing to a provider.
