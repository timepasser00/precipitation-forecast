from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from precip_core.grid import global_grid, res_from_code

from ..fields import Field
from ..grib import decode_grib_bytes, write_grib_message
from ..synth import SyntheticModel


class SyntheticAdapter:
    """Generates fake-but-plausible fields. Every run it produces is flagged ``synthetic``.

    With ``as_grib=True`` (the default) each field is written to an in-memory GRIB2 message and
    decoded again, so the real decoding path is exercised end to end.
    """

    synthetic = True

    def __init__(self, source_id: str, *, as_grib: bool = True, seed: int = 7):
        self.model = SyntheticModel(source_id, seed=seed)
        self.as_grib = as_grib

    def latest_run(self, steps: list[int]) -> datetime:
        now = datetime.now(UTC)
        return (now - timedelta(hours=now.hour % 6)).replace(minute=0, second=0, microsecond=0)

    def iter_fields(self, run_time: datetime, resolution: str, steps: list[int]) -> Iterator[Field]:
        grid = global_grid(res_from_code(resolution))
        for step, acc in self.model.accumulations(run_time, grid, steps):
            if self.as_grib:
                field = decode_grib_bytes(write_grib_message(acc, grid, step, run_time))
            else:
                field = Field(step=step, values=acc, grid=grid, run_time=run_time)
            yield field
