"""The manifest: the one small mutable file that says which immutable run data is current."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from .codec import Encoding
from .storage import CACHE_MANIFEST, NotFound, Storage

MANIFEST_KEY = "manifest.json"
SCHEMA_VERSION = 1


def run_id(run_time: datetime) -> str:
    """UTC start time as YYYYMMDDHH."""
    return run_time.astimezone(UTC).strftime("%Y%m%d%H")


def parse_run_id(rid: str) -> datetime:
    return datetime.strptime(rid, "%Y%m%d%H").replace(tzinfo=UTC)


class TileConfig(BaseModel):
    size: int = 256
    crs: Literal["web-mercator"] = "web-mercator"
    frames_per_chunk: int = 8
    atlas_cols: int = 4


class Frame(BaseModel):
    start: datetime
    end: datetime
    start_h: int
    end_h: int
    kind: Literal["interval", "daily"]


class TierEntry(BaseModel):
    id: str
    name: str
    resolution_deg: float
    bbox: tuple[float, float, float, float]
    zoom_min: int
    zoom_max: int
    grid: dict
    frames: list[Frame]
    chunks: int
    tiles: dict[str, list[tuple[int, int]]] = Field(
        description="Tile coordinates that exist, keyed by zoom level."
    )
    tile_path: str = Field(description="Template with {z}, {x}, {y}, {chunk}.")
    cube_path: str
    bytes: int = 0


class RunEntry(BaseModel):
    run_time: datetime
    status: Literal["partial", "complete"]
    synthetic: bool = False
    published_at: datetime
    tiers: dict[str, TierEntry] = {}


class SourceEntry(BaseModel):
    latest: str | None = None
    previous: str | None = None
    runs: dict[str, RunEntry] = {}


class Manifest(BaseModel):
    schema_version: int = SCHEMA_VERSION
    generated_at: datetime
    encoding: Encoding = Encoding()
    tile: TileConfig = TileConfig()
    sources: dict[str, SourceEntry] = {}

    @classmethod
    def empty(cls) -> Manifest:
        return cls(generated_at=datetime.now(UTC))

    def source(self, source_id: str) -> SourceEntry:
        return self.sources.setdefault(source_id, SourceEntry())

    def refresh_pointers(self, source_id: str, required_tiers: set[str]) -> None:
        """Set ``latest`` and ``previous`` to the two newest runs with all required tiers."""
        entry = self.source(source_id)
        ready = sorted(
            (rid for rid, r in entry.runs.items() if required_tiers <= set(r.tiers)),
            reverse=True,
        )
        for rid in ready:
            entry.runs[rid].status = "complete"
        entry.latest = ready[0] if ready else None
        entry.previous = ready[1] if len(ready) > 1 else None

    def prune(self, source_id: str, keep: int = 2) -> list[str]:
        """Drop runs older than the ``keep`` newest complete ones (in-progress newer runs stay)."""
        entry = self.source(source_id)
        complete = sorted(
            (rid for rid, r in entry.runs.items() if r.status == "complete"), reverse=True
        )
        cutoff = complete[keep - 1] if len(complete) >= keep else None
        removed = [rid for rid in entry.runs if cutoff is not None and rid < cutoff]
        for rid in removed:
            del entry.runs[rid]
        return sorted(removed)


def load_manifest(storage: Storage) -> Manifest:
    try:
        return Manifest.model_validate_json(storage.get(MANIFEST_KEY))
    except NotFound:
        return Manifest.empty()


def save_manifest(storage: Storage, manifest: Manifest) -> None:
    manifest.generated_at = datetime.now(UTC)
    storage.put(
        MANIFEST_KEY,
        manifest.model_dump_json(indent=None).encode(),
        content_type="application/json",
        cache_control=CACHE_MANIFEST,
    )
