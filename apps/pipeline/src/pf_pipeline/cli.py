"""Command line entry point: ``pf-pipeline run|status|inspect|sample``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime

from precip_core.manifest import load_manifest, parse_run_id
from precip_core.registry import load_registry
from precip_core.storage import storage_from_url

from .adapters import make_adapter
from .fields import PipelineError
from .runner import run_source


def _longest_steps(spec) -> list[int]:
    """Steps of the run hour with the longest forecast (IFS 00/12z), used to find 'latest'.

    IFS 06/18z runs only reach 90 h, so 'latest' skips them; request them with --run.
    """
    return max(
        (spec.steps_for(datetime(2026, 1, 1, h, tzinfo=UTC)) for h in spec.run_hours),
        key=lambda steps: steps[-1],
    )


def _storage(url: str | None):
    return storage_from_url(url or os.environ.get("PF_STORAGE_URL", "data/processed"))


def cmd_run(args) -> int:
    reg = load_registry(args.config)
    storage = _storage(args.storage)
    if (
        args.synthetic
        and str(args.storage or os.environ.get("PF_STORAGE_URL", "")).startswith("s3://")
        and not args.allow_synthetic_remote
    ):
        raise PipelineError("refusing to publish synthetic data to remote storage")
    ids = args.source or [s.id for s in reg.sources if s.enabled]
    tiers = set(args.tiers.split(",")) if args.tiers else None
    failures = 0
    for sid in ids:
        spec = reg.source(sid)
        kwargs = {} if args.synthetic else ({"access": args.access} if args.access else {})
        adapter = make_adapter(spec, synthetic=args.synthetic, **kwargs)
        if args.run == "latest":
            runs = [adapter.latest_run(_longest_steps(spec))]
        else:
            runs = [parse_run_id(r) for r in args.run.split(",")]
        for run_time in runs:
            try:
                run_source(reg, spec, adapter, run_time, storage, tiers=tiers, workers=args.workers)
            except PipelineError as e:
                logging.error("%s %s failed: %s", sid, run_time, e)
                failures += 1
    return 1 if failures else 0


def cmd_status(args) -> int:
    m = load_manifest(_storage(args.storage))
    if not m.sources:
        print("manifest is empty")
        return 0
    print(f"manifest generated {m.generated_at:%Y-%m-%d %H:%M}Z")
    for sid, e in sorted(m.sources.items()):
        print(f"{sid}: latest={e.latest} previous={e.previous}")
        for rid, r in sorted(e.runs.items()):
            tag = " SYNTHETIC" if r.synthetic else ""
            print(
                f"  {rid} {r.status}{tag} tiers={sorted(r.tiers)} "
                f"bytes={sum(t.bytes for t in r.tiers.values())}"
            )
    return 0


def cmd_inspect(args) -> int:
    from .sample import inspect_file

    bad = 0
    for p in args.paths:
        lines, failures = inspect_file(p)
        print("\n".join(lines))
        bad += bool(failures)
    return 1 if bad else 0


def cmd_sample(args) -> int:
    from .sample import run_sample

    path, ok = run_sample(
        args.out,
        models=args.models.split(","),
        steps=[int(s) for s in args.steps.split(",")],
        resolution=args.resol,
        access=args.access,
    )
    print(path.read_text())
    print(f"report written to {path}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pf-pipeline", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="fetch, build and publish runs")
    r.add_argument("--source", action="append", help="source id (repeatable); default: all enabled")
    r.add_argument("--run", default="latest", help="'latest' or comma-separated YYYYMMDDHH")
    r.add_argument("--synthetic", action="store_true", help="use generated demo data (flagged)")
    r.add_argument("--allow-synthetic-remote", action="store_true")
    r.add_argument("--access", help="force one access path (ecmwf, aws, google, azure)")
    r.add_argument("--tiers", help="comma-separated tier ids")
    r.add_argument("--storage", help="path, file:// or s3://bucket/prefix?endpoint_url=...")
    r.add_argument("--config", help="path to sources.yaml")
    r.add_argument("--workers", type=int, default=8)
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("status", help="print what the manifest currently holds")
    s.add_argument("--storage")
    s.set_defaults(fn=cmd_status)

    i = sub.add_parser("inspect", help="inspect GRIB files and check our assumptions")
    i.add_argument("paths", nargs="+")
    i.set_defaults(fn=cmd_inspect)

    m = sub.add_parser("sample", help="download real tp fields from ECMWF and check assumptions")
    m.add_argument("--out", default="data/raw/sample")
    m.add_argument("--models", default="ifs,aifs-single")
    m.add_argument("--steps", default="6,12,24,48")
    m.add_argument("--resol", default="0p25")
    m.add_argument("--access", default="ecmwf", help="ecmwf, aws, google or azure")
    m.set_defaults(fn=cmd_sample)

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return args.fn(args)
    except PipelineError as e:
        logging.error("%s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
