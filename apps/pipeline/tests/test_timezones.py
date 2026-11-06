"""Run times are UTC no matter what zone the machine is in.

Regression: ecmwf-opendata returns a naive UTC datetime from ``latest()``; ``.astimezone(UTC)``
treated it as local time, so on an IST machine run 12:00 became 06:30 and the file check failed.
"""

import time
from datetime import UTC, datetime

import pytest
from test_ecmwf_adapter_cli import FakeClient

from pf_pipeline.adapters.ecmwf import EcmwfAdapter
from precip_core.manifest import as_utc, run_id


@pytest.fixture(params=["Asia/Calcutta", "America/Los_Angeles", "UTC"])
def tz(request, monkeypatch):
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield request.param
    monkeypatch.undo()
    time.tzset()


def test_naive_datetimes_are_taken_as_utc(tz):
    assert as_utc(datetime(2026, 11, 5, 12)) == datetime(2026, 11, 5, 12, tzinfo=UTC)
    assert run_id(datetime(2026, 11, 5, 12)) == "2026110512"


def test_aware_datetimes_are_converted(tz):
    from datetime import timedelta, timezone

    ist = timezone(timedelta(hours=5, minutes=30))
    assert as_utc(datetime(2026, 11, 5, 17, 30, tzinfo=ist)) == datetime(
        2026, 11, 5, 12, tzinfo=UTC
    )


def test_latest_run_from_a_naive_client_is_utc(reg, tz):
    class NaiveClient(FakeClient):
        def latest(self, request=None, **kw):
            return datetime(2026, 11, 5, 12)  # what ecmwf-opendata really returns

    adapter = EcmwfAdapter(reg.source("test-src"), client_factory=NaiveClient)
    got = adapter.latest_run([6, 12])
    assert got == datetime(2026, 11, 5, 12, tzinfo=UTC) and got.tzinfo is not None
