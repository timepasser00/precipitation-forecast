"""FastAPI application: a thin read-only layer over what the pipeline published."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from precip_core.manifest import Manifest, RunEntry, TierEntry, parse_run_id
from precip_core.storage import CACHE_IMMUTABLE, CACHE_MANIFEST, NotFound, Storage

from .models import (
    ClientConfig,
    Health,
    PointForecast,
    PointFrame,
    Problem,
    SourceInfo,
)
from .sampling import sample_point
from .settings import Settings
from .state import AppState

API_DESCRIPTION = """
Read-only API over processed ECMWF open-data precipitation forecasts.

**How it fits together.** A pipeline publishes immutable run data (map tiles and point cubes)
plus a small `manifest.json` to object storage. Map clients read the manifest and fetch tiles
straight from the CDN; this API answers the questions a browser should not have to compute:
point forecasts.

**Caching.** Responses for a pinned `run` are immutable and cached for a year. Responses that
follow `latest` are cached for 60 seconds.

**Units and time.** Rainfall is in millimetres over each frame's `[start, end)` window.
All timestamps are UTC (ISO 8601).
"""

HORIZONS_H = (24, 48, 72, 120, 168)
CACHE_LATEST = CACHE_MANIFEST  # public, max-age=60

LatQ = Annotated[float, Query(ge=-90, le=90, description="Latitude, degrees north.")]
LonQ = Annotated[float, Query(ge=-180, le=360, description="Longitude, degrees east.")]


def get_state(request: Request) -> AppState:
    return request.app.state.pf


St = Annotated[AppState, Depends(get_state)]


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    settings = settings or Settings()
    state = AppState(settings, storage)

    app = FastAPI(
        title="Precipitation Forecast API",
        version="0.1.0",
        description=API_DESCRIPTION,
        openapi_tags=[
            {"name": "meta", "description": "Health and client configuration."},
            {"name": "forecast", "description": "Sources, manifest and point forecasts."},
            {"name": "data", "description": "Raw tile/cube objects (development only)."},
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.state.pf = state

    # -- helpers ---------------------------------------------------------------------------

    def resolve_run(m: Manifest, source: str, run: str | None) -> tuple[str, RunEntry]:
        entry = m.sources.get(source)
        if entry is None:
            raise HTTPException(404, f"unknown source {source!r}")
        rid = run or entry.latest
        if rid is None:
            raise HTTPException(404, f"{source}: no run has been published yet")
        r = entry.runs.get(rid)
        if r is None:
            raise HTTPException(404, f"{source}: run {rid} is not available")
        return rid, r

    def pick_tier(run: RunEntry, tier: str | None) -> list[TierEntry]:
        if tier:
            t = run.tiers.get(tier)
            if t is None:
                raise HTTPException(404, f"tier {tier!r} not published for this run")
            return [t]
        return sorted(run.tiers.values(), key=lambda t: t.resolution_deg)  # finest first

    def attribution(source: str) -> str | None:
        reg = state.registry()
        try:
            return reg.source(source).license.attribution if reg else None
        except KeyError:
            return None

    def point_forecast(source: str, run: str | None, tier: str | None, lat: float, lon: float):
        m = state.manifest()
        rid, r = resolve_run(m, source, run)
        for t in pick_tier(r, tier):
            try:
                cube = state.cube(source, rid, t.id, t.cube_path)
            except NotFound as e:
                raise HTTPException(503, f"{source}/{rid}/{t.id}: cube missing in storage") from e
            mm = sample_point(cube, lat, lon)
            if mm is None:
                continue  # outside this tier; try the next coarser one
            frames = [
                PointFrame(
                    start=f.start, end=f.end, kind=f.kind,
                    mm=None if v != v else round(float(v), 2),
                )
                for f, v in zip(t.frames, mm, strict=True)
            ]  # fmt: skip
            t0 = t.frames[0].start
            totals = {}
            for h in HORIZONS_H:
                covered = [f for f in frames if f.end <= t0 + timedelta(hours=h)]
                if covered and covered[-1].end == t0 + timedelta(hours=h):
                    totals[f"{h}h"] = round(sum(f.mm or 0.0 for f in covered), 1)
            return PointForecast(
                source=source, run=rid, run_time=parse_run_id(rid), tier=t.id,
                resolution_deg=t.resolution_deg, lat=lat, lon=lon, synthetic=r.synthetic,
                frames=frames, totals_mm=totals, attribution=attribution(source),
            )  # fmt: skip
        raise HTTPException(404, f"({lat}, {lon}) is outside the area covered by {source}")

    def cache(response: Response, pinned: bool) -> None:
        response.headers["Cache-Control"] = CACHE_IMMUTABLE if pinned else CACHE_LATEST

    # -- meta ------------------------------------------------------------------------------

    @app.get("/healthz", response_model=Health, tags=["meta"], summary="Liveness and data check")
    def healthz(st: St) -> Health:
        m = st.manifest()
        return Health(has_data=any(s.latest for s in m.sources.values()))

    @app.get("/v1/config", response_model=ClientConfig, tags=["meta"], summary="Client bootstrap")
    def client_config(st: St, response: Response) -> ClientConfig:
        response.headers["Cache-Control"] = "public, max-age=300"
        base = st.settings.data_base_url.rstrip("/")
        return ClientConfig(data_base_url=base, manifest_url=f"{base}/manifest.json")

    # -- forecast --------------------------------------------------------------------------

    @app.get("/v1/manifest", response_model=Manifest, tags=["forecast"], summary="Published data")
    def get_manifest(st: St, response: Response) -> Manifest:
        """The same document map clients read from the CDN, for convenience and debugging."""
        cache(response, pinned=False)
        return st.manifest()

    @app.get("/v1/sources", response_model=list[SourceInfo], tags=["forecast"], summary="Sources")
    def list_sources(st: St, response: Response) -> list[SourceInfo]:
        cache(response, pinned=False)
        m = st.manifest()
        reg = st.registry()
        out: list[SourceInfo] = []
        for sid, entry in sorted(m.sources.items()):
            info = SourceInfo(id=sid, latest_run=entry.latest, previous_run=entry.previous)
            if entry.latest:
                run = entry.runs[entry.latest]
                info.latest_run_time, info.synthetic = run.run_time, run.synthetic
                info.tiers = sorted(run.tiers)
            if reg:
                try:
                    spec = reg.source(sid)
                except KeyError:
                    spec = None
                if spec:
                    info.name, info.provider, info.kind = spec.name, spec.provider, spec.kind
                    info.description = spec.description or None
                    info.attribution = spec.license.attribution
                    info.attribution_verified = spec.license.attribution_verified
            out.append(info)
        return out

    @app.get(
        "/v1/point",
        response_model=PointForecast,
        responses={404: {"model": Problem}},
        tags=["forecast"],
        summary="Forecast at one location",
    )
    def point(
        st: St,
        response: Response,
        lat: LatQ,
        lon: LonQ,
        source: Annotated[str, Query(description="Source id, e.g. ecmwf-ifs.")] = "ecmwf-ifs",
        run: Annotated[
            str | None, Query(pattern=r"^\d{10}$", description="Run id; default latest.")
        ] = None,
        tier: Annotated[
            str | None, Query(description="Force a tier; default the finest covering the point.")
        ] = None,
    ) -> PointForecast:
        """Rainfall per frame (3-hourly to 24-hourly, depending on tier and lead time) at a
        location, bilinearly interpolated from the finest published grid that covers it."""
        cache(response, pinned=run is not None)
        return point_forecast(source, run, tier, lat, lon)

    # -- development data proxy ------------------------------------------------------------

    if settings.serve_data:

        @app.get("/data/{path:path}", tags=["data"], summary="Raw object (dev only)")
        def data(path: str, st: St, request: Request) -> Response:
            try:
                body = st.storage.get(path)
            except (NotFound, ValueError) as e:
                raise HTTPException(404, "not found") from e
            ctype = (
                "image/png" if path.endswith(".png")
                else "application/json" if path.endswith(".json")
                else "application/octet-stream"
            )  # fmt: skip
            cc = CACHE_MANIFEST if path == "manifest.json" else CACHE_IMMUTABLE
            return Response(body, media_type=ctype, headers={"Cache-Control": cc})

    return app
