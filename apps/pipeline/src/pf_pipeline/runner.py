"""Process one run of one source and publish it.

Order of operations (see docs/DESIGN.md section 6.2): fetch, derive, build tiers, upload objects
to versioned immutable paths, and only then flip the manifest. A crash at any point leaves the
previously published run untouched.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import numpy as np

from precip_core.grid import coarsen2, crop_grid, res_from_code
from precip_core.manifest import (
    Frame,
    RunEntry,
    TierEntry,
    as_utc,
    load_manifest,
    run_id,
    save_manifest,
)
from precip_core.registry import Registry, SourceSpec, TierSpec
from precip_core.storage import CACHE_IMMUTABLE, Storage

from .adapters import SourceAdapter
from .build import TierArtifacts, build_tier
from .derive import FrameWindow, plan_windows, required_steps, windows_to_mm
from .fields import Field, PipelineError

log = logging.getLogger(__name__)


def to_tier_grid(field: Field, tier: TierSpec, expected_res: float):
    """Coarsen (if the tier is coarser than the source) and crop to the tier's region."""
    if abs(field.grid.dlat - expected_res) > 1e-6 or abs(field.grid.dlon - expected_res) > 1e-6:
        raise PipelineError(
            f"source grid is {field.grid.dlat} x {field.grid.dlon} degrees, expected {expected_res}"
        )
    values, grid = field.values, field.grid
    if abs(tier.resolution_deg - expected_res) < 1e-9:
        pass
    elif abs(tier.resolution_deg - 2 * expected_res) < 1e-9:
        values, grid = coarsen2(values, grid)
    else:
        raise PipelineError(
            f"tier {tier.id}: resolution {tier.resolution_deg} must equal or be twice the source's"
        )
    sub, rows, cols = crop_grid(grid, tier.bbox)
    return np.ascontiguousarray(values[rows, cols]), sub


def _check_not_mixing(storage: Storage, spec: SourceSpec, synthetic: bool) -> None:
    entry = load_manifest(storage).sources.get(spec.id)
    if entry and any(r.synthetic != synthetic for r in entry.runs.values()):
        kind = "synthetic" if synthetic else "real"
        raise PipelineError(
            f"storage already holds {'real' if synthetic else 'synthetic'} runs for {spec.id}; "
            f"refusing to publish {kind} data next to them. Use a separate storage location."
        )


def _upload(storage: Storage, prefix: str, art: TierArtifacts, workers: int) -> None:
    def put(item: tuple[str, bytes]) -> None:
        key, data = item
        ctype = "image/png" if key.endswith(".png") else "application/octet-stream"
        storage.put(f"{prefix}/{key}", data, content_type=ctype, cache_control=CACHE_IMMUTABLE)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(put, art.objects.items()))


def _register_tier(
    storage: Storage,
    reg: Registry,
    spec: SourceSpec,
    rid: str,
    run_time: datetime,
    tier: TierSpec,
    windows: list[FrameWindow],
    art: TierArtifacts,
    synthetic: bool,
) -> list[str]:
    manifest = load_manifest(storage)
    manifest.encoding, manifest.tile = reg.encoding, reg.tile
    entry = manifest.source(spec.id)
    run = entry.runs.get(rid) or RunEntry(
        run_time=run_time, status="partial", synthetic=synthetic, published_at=datetime.now(UTC)
    )
    prefix = f"runs/{spec.id}/{rid}/{tier.id}"
    run.tiers[tier.id] = TierEntry(
        id=tier.id,
        name=tier.name,
        resolution_deg=tier.resolution_deg,
        bbox=tier.bbox,
        zoom_min=tier.zoom_min,
        zoom_max=tier.zoom_max,
        grid=art.grid.to_dict(),
        frames=[
            Frame(
                start=run_time + timedelta(hours=w.start_h),
                end=run_time + timedelta(hours=w.end_h),
                start_h=w.start_h,
                end_h=w.end_h,
                kind=w.kind,  # type: ignore[arg-type]
            )
            for w in windows
        ],
        chunks=art.chunks,
        tiles={str(z): xy for z, xy in art.tiles.items()},
        tile_path=f"{prefix}/{{z}}/{{x}}/{{y}}/c{{chunk}}.png",
        cube_path=f"{prefix}/cube.pfc",
        bytes=art.total_bytes,
    )
    entry.runs[rid] = run
    manifest.refresh_pointers(spec.id, reg.required_tier_ids(spec.id))
    removed = manifest.prune(spec.id, reg.retention.keep_runs)
    save_manifest(storage, manifest)  # the single, atomic publish step
    return removed


def run_source(
    reg: Registry,
    spec: SourceSpec,
    adapter: SourceAdapter,
    run_time: datetime,
    storage: Storage,
    *,
    tiers: set[str] | None = None,
    workers: int = 8,
) -> dict[str, dict]:
    """Fetch, build and publish every selected tier of one run. Returns a per-tier summary."""
    run_time = as_utc(run_time)
    rid = run_id(run_time)
    synthetic = bool(adapter.synthetic)
    _check_not_mixing(storage, spec, synthetic)

    steps = set(spec.steps_for(run_time))
    selected = [t for t in reg.tiers_for(spec.id) if tiers is None or t.id in tiers]
    if not selected:
        raise PipelineError(f"{spec.id}: no tiers selected")
    by_resolution: dict[str, list[TierSpec]] = defaultdict(list)
    for t in selected:
        by_resolution[t.source_resolution].append(t)

    summary: dict[str, dict] = {}
    for resolution, group in by_resolution.items():
        expected = res_from_code(resolution)
        plans = {
            t.id: plan_windows(steps, t.fine_step_h, t.fine_until_h, t.daily_until_h) for t in group
        }
        need = {t.id: required_steps(plans[t.id]) for t in group}
        fetch = sorted(set().union(*need.values()))
        t0 = time.monotonic()
        log.info("%s %s %s: fetching %d steps", spec.id, rid, resolution, len(fetch))

        acc: dict[str, dict[int, np.ndarray]] = {t.id: {} for t in group}
        noise: dict[int, float] = {}
        grids = {}
        for field in adapter.iter_fields(run_time, resolution, fetch):
            if field.meta.get("missing_fraction", 0) > 0.01:
                raise PipelineError(f"step {field.step}: more than 1% missing values")
            noise[field.step] = float(field.meta.get("packing_step_mm", 0.0))
            for t in group:
                if field.step in need[t.id]:
                    acc[t.id][field.step], grids[t.id] = to_tier_grid(field, t, expected)
        log.info("%s %s %s: fetched in %.1fs", spec.id, rid, resolution, time.monotonic() - t0)

        for t in group:
            missing = need[t.id] - acc[t.id].keys()
            if missing:
                raise PipelineError(f"{spec.id}/{t.id}: missing steps {sorted(missing)}")
            t1 = time.monotonic()
            frames_mm, quality = windows_to_mm(acc[t.id], plans[t.id], noise)
            art = build_tier(t, grids[t.id], frames_mm, reg.tile, reg.encoding)
            _upload(storage, f"runs/{spec.id}/{rid}/{t.id}", art, workers)
            removed = _register_tier(
                storage, reg, spec, rid, run_time, t, plans[t.id], art, synthetic
            )
            for old in removed:
                storage.delete_prefix(f"runs/{spec.id}/{old}")
            summary[t.id] = {
                "frames": quality.frames,
                "objects": len(art.objects),
                "bytes": art.total_bytes,
                "max_mm": round(quality.max_mm, 1),
                "wet_fraction": round(quality.wet_fraction, 3),
                "seconds": round(time.monotonic() - t1, 1),
                "pruned": removed,
            }
            log.info("%s %s %s: published %s", spec.id, rid, t.id, summary[t.id])
    return summary
