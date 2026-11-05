from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from precip_core.grid import GridSpec


@dataclass
class Field:
    """One accumulated total-precipitation field.

    ``values`` are metres of water accumulated from the start of the forecast to ``step``
    hours, on ``grid`` (rows north to south, columns west to east from 0 degrees east).
    """

    step: int
    values: np.ndarray
    grid: GridSpec
    run_time: datetime | None = None
    meta: dict = field(default_factory=dict)


class PipelineError(RuntimeError):
    """A run cannot be processed or published."""
