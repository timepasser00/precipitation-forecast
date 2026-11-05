"""Shared fixtures: a tiny registry on coarse grids so end-to-end tests run in seconds."""

from datetime import UTC, datetime

import pytest
import yaml

from precip_core.registry import Registry
from precip_core.storage import LocalStorage

RUN = datetime(2026, 11, 5, 0, tzinfo=UTC)

MINI = {
    "version": 1,
    "tile": {"size": 32, "frames_per_chunk": 4, "atlas_cols": 2},
    "retention": {"keep_runs": 2},
    "sources": [
        {
            "id": "test-src",
            "name": "Test source",
            "provider": "Test",
            "kind": "physics",
            "adapter": "ecmwf",
            "adapter_options": {"model": "ifs", "stream": "oper", "type": "fc"},
            "access_paths": ["ecmwf", "aws"],
            "resolutions": ["2p0", "1p0"],
            "step_schedules": [{"hours": [0, 6, 12, 18], "ranges": [[0, 48, 6]]}],
            "horizon_h": 48,
            "license": {"name": "CC-BY-4.0", "url": "https://example.org", "attribution": "x"},
        }
    ],
    "tiers": [
        {
            "id": "t0", "name": "Global", "source_resolution": "2p0", "resolution_deg": 4.0,
            "bbox": [-180, -90, 180, 90], "zoom_min": 0, "zoom_max": 1,
            "fine_step_h": 6, "fine_until_h": 24, "daily_until_h": 48, "required": True,
        },
        {
            "id": "t1", "name": "India", "source_resolution": "1p0", "resolution_deg": 1.0,
            "bbox": [67, 6, 98, 38], "zoom_min": 3, "zoom_max": 3,
            "fine_step_h": 6, "fine_until_h": 24, "daily_until_h": 48, "required": True,
        },
    ],
}  # fmt: skip


@pytest.fixture
def reg() -> Registry:
    return Registry.model_validate(MINI)


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text(yaml.safe_dump(MINI))
    return p


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "store")
