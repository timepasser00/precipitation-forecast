from datetime import UTC, datetime

import pytest

from precip_core.manifest import (
    Manifest,
    RunEntry,
    TierEntry,
    load_manifest,
    parse_run_id,
    run_id,
    save_manifest,
)
from precip_core.registry import default_config_path, load_registry
from precip_core.storage import LocalStorage, NotFound, S3Storage, storage_from_url

KW = {"content_type": "x/y", "cache_control": "no-store"}


def _exercise(st):
    st.put("a/b/1.bin", b"one", **KW)
    st.put("a/b/2.bin", b"two", **KW)
    st.put("a/c/3.bin", b"three", **KW)
    assert st.get("a/b/1.bin") == b"one"
    assert st.exists("a/b/2.bin") and not st.exists("a/zzz")
    assert st.list("a/b") == ["a/b/1.bin", "a/b/2.bin"]
    assert st.list("nothing") == []
    with pytest.raises(NotFound):
        st.get("a/missing")
    assert st.delete_prefix("a/b") == 2
    assert st.list("a") == ["a/c/3.bin"]


def test_local_storage(tmp_path):
    _exercise(LocalStorage(tmp_path))


def test_local_storage_blocks_path_escape(tmp_path):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).put("../evil", b"x", **KW)


def test_s3_storage_with_moto():
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        c = boto3.client("s3", region_name="us-east-1")
        c.create_bucket(Bucket="pf-test-bucket")
        st = S3Storage("pf-test-bucket", "pfx", client=c)
        _exercise(st)
        st.put("k", b"v", content_type="image/png", cache_control="public, max-age=5")
        head = c.head_object(Bucket="pf-test-bucket", Key="pfx/k")
        assert head["CacheControl"] == "public, max-age=5" and head["ContentType"] == "image/png"


def test_storage_from_url(tmp_path):
    assert isinstance(storage_from_url(str(tmp_path)), LocalStorage)
    assert isinstance(storage_from_url(f"file://{tmp_path}"), LocalStorage)


def _tier(tid):
    return TierEntry(
        id=tid,
        name=tid,
        resolution_deg=0.5,
        bbox=(-180, -90, 180, 90),
        zoom_min=0,
        zoom_max=0,
        grid={},
        frames=[],
        chunks=0,
        tiles={},
        tile_path="t",
        cube_path="c",
    )


def _run(rid, tiers):
    return RunEntry(
        run_time=parse_run_id(rid),
        status="partial",
        published_at=datetime.now(UTC),
        tiers={t: _tier(t) for t in tiers},
    )


def test_manifest_pointers_and_prune():
    m = Manifest.empty()
    e = m.source("s")
    e.runs = {
        "2026110500": _run("2026110500", ["a", "b"]),
        "2026110506": _run("2026110506", ["a", "b"]),
        "2026110512": _run("2026110512", ["a", "b"]),
        "2026110518": _run("2026110518", ["a"]),  # still missing required tier b
    }
    m.refresh_pointers("s", {"a", "b"})
    assert e.latest == "2026110512" and e.previous == "2026110506"
    assert e.runs["2026110518"].status == "partial"
    removed = m.prune("s", keep=2)
    assert removed == ["2026110500"]
    assert set(e.runs) == {"2026110506", "2026110512", "2026110518"}


def test_manifest_roundtrip(tmp_path):
    st = LocalStorage(tmp_path)
    assert load_manifest(st).sources == {}
    m = Manifest.empty()
    m.source("s").runs["2026110500"] = _run("2026110500", ["a"])
    save_manifest(st, m)
    assert load_manifest(st).sources["s"].runs["2026110500"].tiers["a"].id == "a"


def test_run_id_roundtrip():
    t = datetime(2026, 11, 5, 6, tzinfo=UTC)
    assert run_id(t) == "2026110506" and parse_run_id("2026110506") == t


def test_registry_loads_and_schedules():
    reg = load_registry(default_config_path())
    ifs, aifs = reg.source("ecmwf-ifs"), reg.source("ecmwf-aifs")
    s00 = ifs.steps_for(datetime(2026, 11, 5, 0, tzinfo=UTC))
    assert s00[:3] == [0, 3, 6] and s00[-1] == 360 and 147 not in s00 and 150 in s00
    assert ifs.steps_for(datetime(2026, 11, 5, 6, tzinfo=UTC))[-1] == 90
    assert aifs.steps_for(datetime(2026, 11, 5, 18, tzinfo=UTC)) == list(range(0, 361, 6))
    assert [t.id for t in reg.tiers_for("ecmwf-ifs")] == ["t0-global", "t1-south-asia", "t2-india"]
    assert [t.id for t in reg.tiers_for("ecmwf-aifs")] == ["t0-global", "t1-south-asia"]
    assert reg.required_tier_ids("ecmwf-ifs") == {"t0-global", "t1-south-asia"}
    with pytest.raises(ValueError):
        ifs.steps_for(datetime(2026, 11, 5, 3, tzinfo=UTC))
