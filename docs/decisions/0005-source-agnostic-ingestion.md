# 0005: Source-agnostic ingestion and comparison

Status: accepted as baseline (2026-11-06)

## Context
The owner wants to compare different forecast sources and is free to fetch data from wherever it is cheap, good quality and correct. Sources differ in grid, cadence, horizon, retention and licence.

## Decision
- Separate **source** (what we show) from **access path** (where we fetch it). Each source has an ordered list of access paths in config.
- A source registry holds grid, cadence, horizon, variable mapping, licence, attribution text and an enabled flag.
- One adapter per source with a common interface. Downstream code only sees the canonical form (mm per interval, UTC, regular grid).
- Compare mode resamples to a shared grid with an area-weighted method, compares on the coarsest common cadence over the overlapping horizon, and shows each run time.
- A source is enabled only after its licence and terms are checked.

## Alternatives considered
- **Hard-code ECMWF:** simplest now, expensive to generalise later.
- **One aggregator API for all sources:** least work, but the data is reprocessed by a third party, terms must be checked, and we lose control over fidelity and cost.

## Consequences
Adding a source means one adapter plus a registry entry. Pipeline time grows with each source more than storage does. Comparison correctness depends on the resampling choice, which is verified in Phase 3.
