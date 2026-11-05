"""Fixtures: publish a tiny synthetic run (two sources) into a temp store, serve it via the API."""

from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from pf_api.app import create_app
from pf_api.settings import Settings
from pf_pipeline.adapters.synthetic import SyntheticAdapter
from pf_pipeline.runner import run_source
from precip_core.registry import Registry
from precip_core.storage import LocalStorage

RUN = datetime(2026, 11, 5, 0, tzinfo=UTC)


def _source(sid: str, name: str, kind: str) -> dict:
    return {
        "id": sid, "name": name, "provider": "Test", "kind": kind, "adapter": "ecmwf",
        "adapter_options": {"model": "ifs", "stream": "oper", "type": "fc"},
        "access_paths": ["ecmwf"], "resolutions": ["2p0", "1p0"],
        "step_schedules": [{"hours": [0, 6, 12, 18], "ranges": [[0, 48, 6]]}],
        "horizon_h": 48,
        "license": {"name": "CC-BY-4.0", "url": "https://example.org", "attribution": f"{name} data"},
    }  # fmt: skip


CONFIG = {
    "version": 1,
    "tile": {"size": 32, "frames_per_chunk": 4, "atlas_cols": 2},
    "retention": {"keep_runs": 2},
    "sources": [_source("src-a", "Source A", "physics"), _source("src-b", "Source B", "ml")],
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


@pytest.fixture(scope="session")
def published(tmp_path_factory):
    root = tmp_path_factory.mktemp("store")
    cfg = tmp_path_factory.mktemp("cfg") / "sources.yaml"
    cfg.write_text(yaml.safe_dump(CONFIG))
    reg = Registry.model_validate(CONFIG)
    storage = LocalStorage(root)
    for sid in ("src-a", "src-b"):
        run_source(reg, reg.source(sid), SyntheticAdapter(sid), RUN, storage)
    return root, cfg


@pytest.fixture
def client(published):
    root, cfg = published
    settings = Settings(storage_url=str(root), config_path=str(cfg), serve_data=True)
    return TestClient(create_app(settings))


@pytest.fixture
def empty_client(tmp_path):
    return TestClient(create_app(Settings(storage_url=str(tmp_path / "empty"), config_path=None)))
