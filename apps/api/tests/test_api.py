import pytest

DELHI = {"lat": 28.6, "lon": 77.2}  # inside the India tier
LONDON = {"lat": 51.5, "lon": -0.1}  # global tier only


def test_healthz_reports_data(client, empty_client):
    assert client.get("/healthz").json() == {"status": "ok", "has_data": True}
    assert empty_client.get("/healthz").json()["has_data"] is False


def test_config_points_clients_at_the_data_host(client):
    body = client.get("/v1/config").json()
    assert body["manifest_url"] == "/data/manifest.json"


def test_sources_merge_registry_metadata(client):
    by_id = {s["id"]: s for s in client.get("/v1/sources").json()}
    a = by_id["src-a"]
    assert a["name"] == "Source A" and a["kind"] == "physics" and a["synthetic"] is True
    assert a["latest_run"] == "2026110500" and a["previous_run"] is None
    assert a["tiers"] == ["t0", "t1"] and a["attribution"] == "Source A data"
    assert by_id["src-b"]["kind"] == "ml"


def test_sources_work_without_registry(empty_client):
    assert empty_client.get("/v1/sources").json() == []


def test_point_uses_finest_covering_tier(client):
    r = client.get("/v1/point", params={**DELHI, "source": "src-a"})
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] == "t1" and body["resolution_deg"] == 1.0
    assert [f["kind"] for f in body["frames"]] == ["interval"] * 4 + ["daily"]
    assert all(f["mm"] is None or f["mm"] >= 0 for f in body["frames"])
    assert body["totals_mm"].keys() == {"24h", "48h"}
    assert body["totals_mm"]["48h"] >= body["totals_mm"]["24h"]
    assert body["attribution"] == "Source A data"


def test_point_falls_back_to_the_global_tier(client):
    body = client.get("/v1/point", params={**LONDON, "source": "src-a"}).json()
    assert body["tier"] == "t0"


def test_point_totals_equal_sum_of_frames(client):
    body = client.get("/v1/point", params={**DELHI, "source": "src-a"}).json()
    first_day = sum(f["mm"] for f in body["frames"] if f["kind"] == "interval")
    assert body["totals_mm"]["24h"] == pytest.approx(first_day, abs=0.2)


def test_forced_tier_is_honoured(client):
    fine = client.get("/v1/point", params={**DELHI, "source": "src-a", "tier": "t1"}).json()
    coarse = client.get("/v1/point", params={**DELHI, "source": "src-a", "tier": "t0"}).json()
    assert fine["tier"] == "t1" and coarse["tier"] == "t0"
    assert len(fine["frames"]) == len(coarse["frames"])


def test_longitude_conventions_are_equivalent(client):
    a = client.get("/v1/point", params={"lat": 51.5, "lon": -0.1, "source": "src-a"}).json()
    b = client.get("/v1/point", params={"lat": 51.5, "lon": 359.9, "source": "src-a"}).json()
    assert [f["mm"] for f in a["frames"]] == [f["mm"] for f in b["frames"]]


def test_cache_headers_follow_pinning(client):
    latest = client.get("/v1/point", params={**DELHI, "source": "src-a"})
    pinned = client.get("/v1/point", params={**DELHI, "source": "src-a", "run": "2026110500"})
    assert latest.headers["cache-control"] == "public, max-age=60"
    assert "immutable" in pinned.headers["cache-control"]


@pytest.mark.parametrize(
    "params, status",
    [
        ({"lat": 91, "lon": 0}, 422),
        ({"lat": 0, "lon": 400}, 422),
        ({"lat": 0, "lon": 0, "source": "nope"}, 404),
        ({"lat": 0, "lon": 0, "source": "src-a", "run": "2000010100"}, 404),
        ({"lat": 0, "lon": 0, "source": "src-a", "run": "bad"}, 422),
        ({"lat": 0, "lon": 0, "source": "src-a", "tier": "t9"}, 404),
        ({"lat": 28.6, "lon": 77.2, "source": "src-a", "tier": "t0"}, 200),
    ],
)
def test_point_errors(client, params, status):
    assert client.get("/v1/point", params=params).status_code == status


def test_point_outside_a_forced_regional_tier_is_404(client):
    r = client.get("/v1/point", params={**LONDON, "source": "src-a", "tier": "t1"})
    assert r.status_code == 404 and "outside" in r.json()["detail"]


def test_point_before_any_publish_is_404(empty_client):
    assert empty_client.get("/v1/point", params={"lat": 0, "lon": 0}).status_code == 404


def test_manifest_passthrough(client):
    m = client.get("/v1/manifest").json()
    assert m["schema_version"] == 1 and set(m["sources"]) == {"src-a", "src-b"}


def test_dev_data_proxy_serves_tiles_with_immutable_caching(client):
    m = client.get("/v1/manifest").json()
    t = m["sources"]["src-a"]["runs"]["2026110500"]["tiers"]["t1"]
    (x, y), z = t["tiles"]["3"][0], 3
    path = "/data/" + t["tile_path"].format(z=z, x=x, y=y, chunk=0)
    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:4] == b"\x89PNG" and "immutable" in r.headers["cache-control"]
    assert client.get("/data/manifest.json").headers["cache-control"] == "public, max-age=60"
    assert client.get("/data/../../etc/passwd").status_code in (404, 400)
    assert client.get("/data/nope.png").status_code == 404


def test_data_proxy_is_off_by_default(published):
    from fastapi.testclient import TestClient

    from pf_api.app import create_app
    from pf_api.settings import Settings

    root, _ = published
    c = TestClient(create_app(Settings(storage_url=str(root))))
    assert c.get("/data/manifest.json").status_code == 404


def test_openapi_documents_the_contract(client):
    spec = client.get("/openapi.json").json()
    assert {"/v1/point", "/v1/sources", "/v1/manifest", "/v1/config"} <= set(spec["paths"])
    assert "PointForecast" in spec["components"]["schemas"]


def test_committed_openapi_file_is_current():
    """packages/api-contract/openapi.json is the contract the Angular client is generated from."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "scripts" / "export_openapi.py"
    spec = importlib.util.spec_from_file_location("export_openapi", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.TARGET.exists(), "run `make openapi`"
    assert mod.TARGET.read_text() == mod.generate(), (
        "stale packages/api-contract/openapi.json: run `make openapi`"
    )
