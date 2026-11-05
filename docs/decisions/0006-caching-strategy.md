# 0006: Caching strategy

Status: accepted as baseline (2026-11-06)

## Context
R2 is object storage, not a cache. Cloudflare caches by file extension by default, does not cache JSON or unlisted extensions, and applies a 120-minute edge TTL when no `Cache-Control` is sent. The `r2.dev` URL is non-production, rate-limited and uncached. Range-request caching has conditions and unclear cold-miss behaviour.

## Decision
- Layered caching: browser memory, browser HTTP cache, app shell, Cloudflare edge, API response headers, then R2 as origin on a miss (details in DESIGN.md section 6.3).
- Immutable versioned keys with long TTLs. The manifest is the only mutable object, with a short TTL.
- Custom domain on the bucket, an explicit Cache Rule, explicit `Cache-Control` on everything, tiered caching if available on our plan.
- Medium-size objects fetched whole by default. Byte-range reads of larger packs only if a Phase 3 spike shows they cache well.
- Point queries are keyed by grid cell, not raw lat/lon.
- Target hit ratio at or above 95%, with an automated check on headers and cache hits.

## Alternatives considered
- **Rely on R2 alone:** every request becomes a billed origin read.
- **Purge-based invalidation:** adds operational work. Immutable keys avoid it.
- **Short TTLs everywhere:** simple but defeats the cost model.

## Consequences
Cache correctness becomes a tested requirement. A new run starts cold, so the first users pay a miss, which pre-warming can soften.
