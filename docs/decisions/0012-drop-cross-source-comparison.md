# 0012: Drop cross-source comparison

Status: decided by the owner (2026-11-06)

## Context
The design started with comparison between sources (side by side, difference maps, overlaid
point charts) as a first-class feature. The first real run showed why it is hard: latest IFS was
the 12z run with 3-hourly frames, latest AIFS the 18z run with 6-hourly frames, so frames and
`24h` totals covered different real-world periods. A faithful comparison needs either matching
initialisation times or a common valid-time axis, plus resampling to a shared grid.

## Decision
Show one source at a time, with a switch between sources. Do not build comparison. Remove
`/v1/compare`, goal G5's comparison wording, FR5, and the compare-mode UI.

## What stays
Source-agnostic ingestion (ADR 0005): sources and access paths remain configurable, and more
sources can still be added and switched between. The canonical form per source is unchanged.

## Consequences
- Simpler API, UI and pipeline; no shared-grid resampling work.
- Each source keeps its own latest run, so runs for different sources may differ; the UI must
  show each run's time.
- Reversible: comparison can be added later from the same stored data, using either option
  recorded in the 2026-11-06 discussion (same initialisation time, or a common valid-time axis).
