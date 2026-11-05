"""Check our assumptions against real files: download a few ECMWF tp fields and inspect them.

Run on a machine that can reach ECMWF (this project's CI and sandbox cannot):

    uv run pf-pipeline sample --out data/raw/sample

The report states, key by key, what is in the files and whether each assumption in
docs/data-format.md holds. Nothing here is needed at runtime.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable
from pathlib import Path

import eccodes
import numpy as np

from .grib import GribError, _decode_message

log = logging.getLogger(__name__)

KEYS = [
    "shortName", "paramId", "name", "units", "gridType", "Ni", "Nj",
    "latitudeOfFirstGridPointInDegrees", "latitudeOfLastGridPointInDegrees",
    "longitudeOfFirstGridPointInDegrees", "longitudeOfLastGridPointInDegrees",
    "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees",
    "iScansNegatively", "jScansPositively", "stepType", "startStep", "endStep",
    "stepUnits", "dataDate", "dataTime", "typeOfLevel", "packingType", "bitsPerValue",
]  # fmt: skip


def inspect_file(path: str | Path) -> tuple[list[str], list[str]]:
    """Return (report lines, failed checks) for a GRIB file."""
    lines: list[str] = [f"== {path}"]
    failures: list[str] = []
    means: list[tuple[int, float]] = []
    n = 0
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            n += 1
            try:
                info = {}
                for k in KEYS:
                    try:
                        info[k] = eccodes.codes_get(gid, k)
                    except Exception:
                        info[k] = "<absent>"
                vals = eccodes.codes_get_values(gid)
                lines.append(f"-- message {n}: " + ", ".join(f"{k}={v}" for k, v in info.items()))
                lines.append(
                    f"   values: min={vals.min():.6g} max={vals.max():.6g} mean={vals.mean():.6g}"
                    f" nan={int(np.isnan(vals).sum())}"
                )
                tag = f"message {n} (step {info['endStep']})"
                try:
                    field = _decode_message(gid)
                    lines.append(
                        f"   decoded OK: grid {field.grid.ny}x{field.grid.nx}, "
                        f"lat0={field.grid.lat0}, lon0={field.grid.lon0}, "
                        f"wrap={field.grid.wrap_lon}"
                    )
                    means.append((field.step, float(field.values.mean())))
                    if field.values.min() < -1e-6:
                        failures.append(f"{tag}: negative accumulations")
                    if field.values.max() > 3.0:
                        failures.append(f"{tag}: implausible value > 3 m")
                except GribError as e:
                    failures.append(f"{tag}: decoder rejected it: {e}")
            finally:
                eccodes.codes_release(gid)
    if n == 0:
        failures.append("file contains no GRIB messages")
    means.sort()
    if len(means) > 1:
        lines.append(
            "   global mean tp (m) by step: " + ", ".join(f"{s}h={m:.6f}" for s, m in means)
        )
        if any(b < a - 1e-9 for (_, a), (_, b) in itertools.pairwise(means)):
            failures.append("global mean tp decreases with step: not an accumulation")
    lines.append(f"   checks: {'ALL PASSED' if not failures else 'FAILED'}")
    lines += [f"   FAIL: {x}" for x in failures]
    return lines, failures


def run_sample(
    out: str | Path,
    *,
    models: list[str],
    steps: list[int],
    resolution: str = "0p25",
    access: str = "ecmwf",
    client_factory: Callable[..., object] | None = None,
) -> tuple[Path, bool]:
    """Download tp for each model, inspect, write ``report.txt``. Returns (report path, ok)."""
    if client_factory is None:
        from ecmwf.opendata import Client

        client_factory = Client
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    report: list[str] = [f"access={access} resolution={resolution} steps={steps}"]
    ok = True
    for model in models:
        target = out / f"{model}_{resolution}_tp.grib2"
        try:
            client = client_factory(source=access, model=model, resol=resolution)
            client.retrieve(  # no date/time: the client picks the latest available run
                {"stream": "oper", "type": "fc", "param": "tp", "step": steps}, target=str(target)
            )
        except Exception as e:
            report.append(f"== {model}: DOWNLOAD FAILED: {e}")
            ok = False
            continue
        lines, failures = inspect_file(target)
        report += lines
        ok = ok and not failures
    report.append("OVERALL: " + ("ALL CHECKS PASSED" if ok else "SOMETHING FAILED, see above"))
    path = out / "report.txt"
    path.write_text("\n".join(report) + "\n")
    return path, ok
