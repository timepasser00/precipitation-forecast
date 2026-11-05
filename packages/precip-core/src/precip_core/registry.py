"""Source and tier registry, loaded from ``config/sources.yaml``."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .codec import Encoding
from .grid import BBox
from .manifest import TileConfig


class License(BaseModel):
    name: str
    url: str
    attribution: str
    attribution_verified: bool = False


class StepSchedule(BaseModel):
    hours: list[int]
    ranges: list[tuple[int, int, int]] = Field(description="(first, last inclusive, step) in hours")


class SourceSpec(BaseModel):
    id: str
    name: str
    provider: str
    kind: Literal["physics", "ml"]
    description: str = ""
    enabled: bool = True
    adapter: str
    adapter_options: dict = {}
    access_paths: list[str] = []
    resolutions: list[str]
    step_schedules: list[StepSchedule]
    horizon_h: int
    license: License

    def steps_for(self, run_time: datetime) -> list[int]:
        for sched in self.step_schedules:
            if run_time.hour in sched.hours:
                steps: set[int] = set()
                for first, last, step in sched.ranges:
                    steps.update(range(first, last + 1, step))
                return sorted(steps)
        raise ValueError(f"{self.id}: no step schedule for run hour {run_time.hour}")

    @property
    def run_hours(self) -> list[int]:
        return sorted({h for s in self.step_schedules for h in s.hours})


class TierSpec(BaseModel):
    id: str
    name: str
    source_resolution: str
    resolution_deg: float
    bbox: BBox
    zoom_min: int
    zoom_max: int
    fine_step_h: int
    fine_until_h: int
    daily_until_h: int
    required: bool = True
    sources: list[str] | None = None


class Retention(BaseModel):
    keep_runs: int = 2


class Registry(BaseModel):
    version: int = 1
    encoding: Encoding = Encoding()
    tile: TileConfig = TileConfig()
    retention: Retention = Retention()
    sources: list[SourceSpec]
    tiers: list[TierSpec]

    def source(self, source_id: str) -> SourceSpec:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise KeyError(f"unknown source {source_id!r}")

    def tiers_for(self, source_id: str) -> list[TierSpec]:
        spec = self.source(source_id)
        return [
            t
            for t in self.tiers
            if (t.sources is None or source_id in t.sources)
            and t.source_resolution in spec.resolutions
        ]

    def required_tier_ids(self, source_id: str) -> set[str]:
        return {t.id for t in self.tiers_for(source_id) if t.required}


def default_config_path() -> Path:
    env = os.environ.get("PF_CONFIG")
    if env:
        return Path(env)
    here = Path.cwd().resolve()
    for d in [here, *here.parents]:
        candidate = d / "config" / "sources.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("config/sources.yaml not found; set PF_CONFIG")


def load_registry(path: str | os.PathLike | None = None) -> Registry:
    p = Path(path) if path else default_config_path()
    return Registry.model_validate(yaml.safe_load(p.read_text()))
