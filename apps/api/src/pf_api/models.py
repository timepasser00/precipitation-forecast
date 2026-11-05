"""Response models. These define the public contract and generate the OpenAPI document."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    has_data: bool = Field(description="True once at least one run has been published.")


class ClientConfig(BaseModel):
    data_base_url: str = Field(description="Prefix for every tile and cube path in the manifest.")
    manifest_url: str = Field(description="URL of manifest.json on the data host.")
    api_version: str = "v1"


class SourceInfo(BaseModel):
    id: str
    name: str | None = None
    provider: str | None = None
    kind: Literal["physics", "ml"] | None = None
    description: str | None = None
    latest_run: str | None = Field(None, description="Run id, YYYYMMDDHH (UTC).")
    previous_run: str | None = None
    latest_run_time: datetime | None = None
    synthetic: bool = False
    tiers: list[str] = []
    attribution: str | None = None
    attribution_verified: bool | None = None


class PointFrame(BaseModel):
    start: datetime
    end: datetime
    kind: Literal["interval", "daily"]
    mm: float | None = Field(description="Rainfall over [start, end) in mm; null if no data.")


class PointForecast(BaseModel):
    source: str
    run: str
    run_time: datetime
    tier: str
    resolution_deg: float
    lat: float
    lon: float
    units: Literal["mm"] = "mm"
    synthetic: bool
    frames: list[PointFrame]
    totals_mm: dict[str, float] = Field(
        description="Accumulated rainfall by horizon, e.g. '24h', '72h', '168h'. "
        "Only horizons fully covered by the available frames are present."
    )
    attribution: str | None = None


class SourceError(BaseModel):
    source: str
    error: str


class Comparison(BaseModel):
    lat: float
    lon: float
    results: list[PointForecast]
    errors: list[SourceError] = Field(
        description="Sources that could not answer; the others are still returned."
    )


class Problem(BaseModel):
    detail: str
