from datetime import UTC, datetime

import pytest

from pf_pipeline.adapters import make_adapter
from pf_pipeline.adapters.ecmwf import EcmwfAdapter
from pf_pipeline.cli import main
from pf_pipeline.fields import PipelineError
from pf_pipeline.grib import write_grib_message
from pf_pipeline.synth import SyntheticModel
from precip_core.grid import global_grid
from precip_core.manifest import load_manifest
from precip_core.registry import load_registry
from precip_core.storage import LocalStorage

RUN = datetime(2026, 11, 5, 0, tzinfo=UTC)

G = global_grid(2.0)


def _grib_for(run, steps, skip=()):
    out = b""
    for step, acc in SyntheticModel("ecmwf-ifs").accumulations(run, G, steps):
        if step not in skip:
            out += write_grib_message(acc, G, step, run)
    return out


class FakeClient:
    """Stands in for ecmwf.opendata.Client; records how it was called."""

    calls: list = []

    def __init__(self, source="ecmwf", model="ifs", resol="0p25", **kw):
        self.source, self.model, self.resol = source, model, resol

    def retrieve(self, request=None, target=None, **kw):
        FakeClient.calls.append(("retrieve", self.source, self.model, self.resol, dict(request)))
        if self.source == "ecmwf":
            raise OSError("portal busy")
        run = datetime.strptime(request["date"], "%Y%m%d").replace(hour=request["time"], tzinfo=UTC)
        open(target, "wb").write(_grib_for(run, request["step"], skip=getattr(self, "skip", ())))

    def latest(self, request=None, **kw):
        FakeClient.calls.append(("latest", self.source, dict(request)))
        if self.source == "ecmwf":
            raise OSError("portal busy")
        return RUN


@pytest.fixture(autouse=True)
def _reset():
    FakeClient.calls = []


def _adapter(reg, **kw):
    return EcmwfAdapter(reg.source("test-src"), client_factory=FakeClient, **kw)


def test_request_shape_and_access_path_fallback(reg):
    fields = list(_adapter(reg).iter_fields(RUN, "2p0", [6, 12]))
    assert [f.step for f in fields] == [6, 12]
    kinds = [(c[0], c[1]) for c in FakeClient.calls]
    assert kinds == [("retrieve", "ecmwf"), ("retrieve", "aws")]  # portal failed, mirror worked
    req = FakeClient.calls[-1][4]
    assert req["param"] == "tp" and req["step"] == [6, 12] and req["time"] == 0
    assert req["date"] == "20261105" and req["stream"] == "oper" and req["type"] == "fc"


def test_access_override_and_latest(reg):
    a = _adapter(reg, access="google")
    assert a.latest_run([48]) == RUN
    assert FakeClient.calls[0][:2] == ("latest", "google")
    assert FakeClient.calls[0][2]["step"] == 48


def test_all_access_paths_failing_is_a_pipeline_error(reg):
    spec = reg.source("test-src").model_copy(update={"access_paths": ["ecmwf"]})
    with pytest.raises(PipelineError, match="no access path"):
        list(EcmwfAdapter(spec, client_factory=FakeClient).iter_fields(RUN, "2p0", [6]))


def test_missing_step_in_download_is_detected(reg):
    class Skipping(FakeClient):
        skip = (12,)

    spec = reg.source("test-src").model_copy(update={"access_paths": ["aws"]})
    with pytest.raises(PipelineError, match="missing"):
        list(EcmwfAdapter(spec, client_factory=Skipping).iter_fields(RUN, "2p0", [6, 12]))


def test_file_from_a_different_run_is_rejected(reg):
    class WrongRun(FakeClient):
        def retrieve(self, request=None, target=None, **kw):
            open(target, "wb").write(_grib_for(datetime(2026, 11, 4, 12, tzinfo=UTC), [6]))

    spec = reg.source("test-src").model_copy(update={"access_paths": ["aws"]})
    with pytest.raises(PipelineError, match="expected"):
        list(EcmwfAdapter(spec, client_factory=WrongRun).iter_fields(RUN, "2p0", [6]))


def test_make_adapter_picks_synthetic_or_ecmwf(reg):
    assert make_adapter(reg.source("test-src"), synthetic=True).synthetic is True
    assert make_adapter(reg.source("test-src"), client_factory=FakeClient).synthetic is False


def test_cli_run_status_and_inspect(config_file, tmp_path, capsys):
    store = tmp_path / "out"
    rc = main(["run", "--synthetic", "--source", "test-src", "--run", "2026110500,2026110506",
               "--storage", str(store), "--config", str(config_file)])  # fmt: skip
    assert rc == 0
    m = load_manifest(LocalStorage(store))
    assert (
        m.sources["test-src"].latest == "2026110506"
        and m.sources["test-src"].previous == "2026110500"
    )
    assert main(["status", "--storage", str(store)]) == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out and "latest=2026110506" in out

    grib = tmp_path / "x.grib2"
    grib.write_bytes(_grib_for(RUN, [6, 12, 24]))
    assert main(["inspect", str(grib)]) == 0
    assert "ALL PASSED" in capsys.readouterr().out


def test_cli_refuses_synthetic_to_remote_storage(config_file):
    rc = main(["run", "--synthetic", "--source", "test-src", "--run", "2026110500",
               "--storage", "s3://bucket/x", "--config", str(config_file)])  # fmt: skip
    assert rc == 2


def test_sample_command_reports_pass_and_failure(tmp_path):
    from pf_pipeline.sample import run_sample

    class Good(FakeClient):
        def retrieve(self, request=None, target=None, **kw):
            open(target, "wb").write(_grib_for(RUN, request["step"]))

    path, ok = run_sample(tmp_path / "ok", models=["ifs"], steps=[6, 12], client_factory=Good)
    assert ok and "ALL CHECKS PASSED" in path.read_text()

    class Bad(FakeClient):
        def retrieve(self, request=None, target=None, **kw):
            raise OSError("no route to host")

    path, ok = run_sample(tmp_path / "bad", models=["ifs"], steps=[6], client_factory=Bad)
    assert not ok and "DOWNLOAD FAILED" in path.read_text()


def test_inspect_flags_non_accumulating_files(tmp_path):
    from pf_pipeline.sample import inspect_file

    a6 = dict(SyntheticModel("ecmwf-ifs").accumulations(RUN, G, [48]))[48]
    p = tmp_path / "bad.grib2"
    # step 6 holds MORE rain than step 12: impossible for an accumulation
    p.write_bytes(write_grib_message(a6, G, 6, RUN) + write_grib_message(a6 * 0.1, G, 12, RUN))
    _, failures = inspect_file(p)
    assert any("decreases" in f for f in failures)


def test_real_registry_is_consistent_with_the_cli_defaults():
    reg = load_registry()
    assert {s.id for s in reg.sources if s.enabled} == {"ecmwf-ifs", "ecmwf-aifs"}


def test_missing_model_option_is_a_clear_error(reg):
    spec = reg.source("test-src").model_copy(update={"adapter_options": {}})
    with pytest.raises(PipelineError, match="model is required"):
        EcmwfAdapter(spec, client_factory=FakeClient)
