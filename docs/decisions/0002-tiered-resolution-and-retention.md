# 0002: Tiered resolution, time policy and retention

Status: accepted as baseline (2026-11-06)

## Context
Audience is India. Budget is personal. ECMWF forecasts are global, retained upstream for only 12 runs, and run to 15 days. Detail beyond about day 7 is mostly noise for precipitation.

## Decision
Three tiers (global 0.5°, South Asia 0.25°, India 0.1° IFS), each with overview pyramids. Fine time resolution to day 7, daily totals to day 15. Keep latest and previous run only. Delete raw GRIB after processing. Region boxes and cadences live in configuration.

## Alternatives considered
- **Global 0.25° only:** simpler, but no extra detail where users are, and about 4x more data than needed outside India.
- **Global 0.1°:** about 6x the points of 0.25° with no real gain for AIFS (native about 0.25°) and little gain outside India.
- **On-demand fine tiles:** needs raw high-resolution data retained and per-request compute, which breaks the cost model.
- **30-day history:** conflicts with the forget-the-past policy and is not needed for the product.

## Consequences
Storage is tens of MB, so it is not a cost driver. The pipeline must handle tier-independent publishing. Adding a region or raising detail is a configuration change. Size numbers are estimates to be replaced by measurements in Phase 3.
