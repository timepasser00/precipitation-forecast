"""ECMWF Open Data adapter (IFS and AIFS) using ECMWF's own ``ecmwf-opendata`` client.

The client fetches single fields with HTTP byte ranges, so only total precipitation is
downloaded, not whole files. Files are global: there is no server-side area subsetting.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from precip_core.manifest import as_utc
from precip_core.registry import SourceSpec

from ..fields import Field, PipelineError
from ..grib import decode_grib_file

log = logging.getLogger(__name__)


class EcmwfAdapter:
    synthetic = False

    def __init__(
        self,
        spec: SourceSpec,
        *,
        access: str | None = None,
        workdir: str | Path | None = None,
        client_factory: Callable[..., object] | None = None,
    ):
        self.spec = spec
        self.options = spec.adapter_options
        if "model" not in self.options:
            raise PipelineError(f"{spec.id}: adapter_options.model is required (ifs, aifs-single)")
        self.access_paths = [access] if access else list(spec.access_paths or ["ecmwf"])
        self.workdir = Path(workdir) if workdir else None
        if client_factory is None:
            from ecmwf.opendata import Client

            client_factory = Client
        self._factory = client_factory

    def _client(self, access: str, resolution: str):
        return self._factory(source=access, model=self.options["model"], resol=resolution)

    def _request(self, **extra) -> dict:
        return {
            "stream": self.options.get("stream", "oper"),
            "type": self.options.get("type", "fc"),
            "param": "tp",
            **extra,
        }

    def latest_run(self, steps: list[int]) -> datetime:
        last_error: Exception | None = None
        for access in self.access_paths:
            try:
                res = self.spec.resolutions[0]
                return as_utc(self._client(access, res).latest(self._request(step=max(steps))))
            except Exception as e:
                log.warning("latest() failed via %s: %s", access, e)
                last_error = e
        raise PipelineError(f"{self.spec.id}: no access path worked: {last_error}")

    def iter_fields(self, run_time: datetime, resolution: str, steps: list[int]) -> Iterator[Field]:
        run_time = as_utc(run_time)
        last_error: Exception | None = None
        with tempfile.TemporaryDirectory(dir=self.workdir) as tmp:
            target = Path(tmp) / f"{self.spec.id}_{run_time:%Y%m%d%H}_{resolution}.grib2"
            for access in self.access_paths:
                try:
                    self._client(access, resolution).retrieve(
                        self._request(
                            date=run_time.strftime("%Y%m%d"), time=run_time.hour, step=steps
                        ),
                        target=str(target),
                    )
                    break
                except Exception as e:
                    log.warning("retrieve failed via %s: %s", access, e)
                    last_error = e
            else:
                raise PipelineError(f"{self.spec.id}: no access path worked: {last_error}")
            seen = set()
            for field in decode_grib_file(target):
                if field.run_time and field.run_time != run_time:
                    raise PipelineError(
                        f"{self.spec.id}: file holds run {field.run_time}, expected {run_time}"
                    )
                seen.add(field.step)
                yield field
            missing = set(steps) - seen
            if missing:
                raise PipelineError(
                    f"{self.spec.id}: steps missing from download: {sorted(missing)}"
                )
