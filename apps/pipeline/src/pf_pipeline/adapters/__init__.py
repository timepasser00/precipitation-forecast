"""Source adapters: one small interface per data provider.

An adapter knows how to find the latest run and how to fetch accumulated precipitation fields
for given steps. Everything downstream (derivation, tiling, publishing) only sees ``Field``s.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Protocol

from precip_core.registry import SourceSpec

from ..fields import Field, PipelineError


class SourceAdapter(Protocol):
    synthetic: bool

    def latest_run(self, steps: list[int]) -> datetime:
        """Newest run for which every step in ``steps`` is already available."""
        ...

    def iter_fields(self, run_time: datetime, resolution: str, steps: list[int]) -> Iterator[Field]:
        """Yield accumulated tp fields, one per requested step, in any order."""
        ...


def make_adapter(spec: SourceSpec, *, synthetic: bool = False, **kwargs) -> SourceAdapter:
    if synthetic:
        from .synthetic import SyntheticAdapter

        return SyntheticAdapter(spec.id, **kwargs)
    if spec.adapter == "ecmwf":
        from .ecmwf import EcmwfAdapter

        return EcmwfAdapter(spec, **kwargs)
    raise PipelineError(f"no adapter named {spec.adapter!r} for source {spec.id!r}")
