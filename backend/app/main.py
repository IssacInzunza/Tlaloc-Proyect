"""FastAPI entry point. Bind to loopback; no accounts or telemetry."""
import json
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .checkpoints import TrackingStore
from .geocoding import Geocoder, SearchError
from .history import AlertHistory
from .models import Coverage, Location, ReplayRequest
from .monitoring import MonitorService
from .notifications import NotificationService
from .nowcasting import predict
from .providers import MRMSProvider, ProviderError
from .radar import Frame, coverage, render
from .replay import evaluate
from .tracking import associate, segment, track

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("TLALOC_CACHE", str(ROOT / ".cache")))
provider = MRMSProvider(CACHE)
history = AlertHistory(CACHE / "history.sqlite3")


@asynccontextmanager
async def lifespan(_app):
    notification_service.start()
    monitor_service.start()
    try:
        yield
    finally:
        notification_service.stop()
        monitor_service.stop()


app = FastAPI(title="Tlaloc Project", version="1.0.0",
              description="Experimental NOAA radar tracking. Not an official warning system.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
lock = threading.RLock()
result_cache = {}
tracking_cache = {}
tracking_store = TrackingStore(CACHE / "tracking")
geocoder = Geocoder()


def location_query(lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
                   lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
                   radius_km: Annotated[float, Query(ge=10, le=100)] = 50,
                   threshold: Annotated[float, Query(ge=0.1, le=10)] = 0.2):
    return Location(lat=lat, lon=lon, radius_km=radius_km, threshold=threshold)


LocationQuery = Annotated[Location, Depends(location_query)]


def analyze(location):
    key = history.scope(location)
    with lock:
        cached = result_cache.get(key)
        if cached and time.monotonic()-cached[0] < 60:
            result = dict(cached[1])
            frames = cached[2]
            if frames:
                state = coverage(frames[-1], location)
                tracked = tracking_cache.get(key)
                predictions = predict(frames, location, tracked_regions=tracked[1] if tracked else None)
                result["coverage"] = state.model_dump()
                result["predictions"] = [p.model_dump(mode="json") for p in predictions]
                history.update(location, predictions, frames[-1].time.isoformat(),
                               unavailable=state.status in ("insufficient_coverage", "stale_observations"))
            return result
        started = time.perf_counter()
        frames = []
        try:
            frames = provider.frames(location)
            state = coverage(frames[-1], location) if frames else Coverage(
                status="insufficient_coverage", reason="no_observations")
        except (ProviderError, ValueError, OSError) as error:
            logging.getLogger(__name__).warning("Radar provider failed: %s", type(error).__name__)
            state = Coverage(status="provider_unavailable", reason="provider_error")
        predictions = []
        if frames:
            previous = tracking_cache.get(key) or tracking_store.load(key)
            if previous and frames[-1].time >= previous[0].time:
                previous_frame, tracked = previous
                for frame in frames:
                    if frame.time > previous_frame.time:
                        tracked = associate(previous_frame, frame, tracked, segment(frame, location.threshold))
                        previous_frame = frame
            else:
                tracked = track(frames, location.threshold)
            if len(tracking_cache) >= 8 and key not in tracking_cache:
                tracking_cache.pop(next(iter(tracking_cache)))
            tracking_cache[key] = (frames[-1], tracked)
            if not previous or frames[-1].time > previous[0].time:
                tracking_store.save(key, frames[-1], tracked)
            predictions = predict(frames, location, tracked_regions=tracked)
        serialized = [p.model_dump(mode="json") for p in predictions]
        observation = frames[-1].time.isoformat() if frames else datetime.now(UTC).isoformat()
        history.update(location, predictions, observation,
                       unavailable=state.status in ("provider_unavailable", "insufficient_coverage", "stale_observations"))
        target_rate = None
        if frames:
            value = frames[-1].rate[tuple(size // 2 for size in frames[-1].rate.shape)]
            target_rate = float(value) if np.isfinite(value) else None
        result = {"location": location.model_dump(), "coverage": state.model_dump(), "target_rate": target_rate,
                  "frames": [render(frame, location) for frame in frames], "predictions": serialized,
                  "observation_time": frames[-1].time.isoformat() if frames else None,
                  "processing_seconds": round(time.perf_counter()-started, 3),
                  "unit": "mm/h", "provider": "NOAA MRMS", "experimental": True}
        if len(result_cache) >= 8:
            result_cache.pop(next(iter(result_cache)))
        result_cache[key] = (time.monotonic(), result, frames)
        return result


notification_service = NotificationService(CACHE, analyze)
app.include_router(notification_service.router)
monitor_service = MonitorService(CACHE / "monitoring", analyze)
app.include_router(monitor_service.router)


@app.middleware("http")
async def fresh_api(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0", "provider": "NOAA MRMS"}


@app.get("/api/analysis")
def analysis(location: LocationQuery):
    return analyze(location)


@app.get("/api/coverage")
def get_coverage(location: LocationQuery):
    return analyze(location)["coverage"]


@app.get("/api/radar/frames")
def get_frames(location: LocationQuery):
    return analyze(location)["frames"]


@app.get("/api/radar/latest")
def get_latest(location: LocationQuery):
    frames = analyze(location)["frames"]
    return frames[-1] if frames else None


@app.get("/api/predictions")
@app.get("/api/precipitation")
@app.get("/api/alerts")
def get_predictions(location: LocationQuery):
    return analyze(location)["predictions"]


@app.get("/api/history")
def get_history(location: LocationQuery):
    return history.list(location)


@app.get("/api/search")
def search(q: Annotated[str, Query(min_length=2, max_length=200)], language: Literal["en", "es"] = "en",
           lat: Annotated[float | None, Query(ge=-90, le=90, allow_inf_nan=False)] = None,
           lon: Annotated[float | None, Query(ge=-180, le=180, allow_inf_nan=False)] = None,
           suggest: bool = False, external: bool = False):
    if not external:
        raise HTTPException(403, "search_consent_required")
    try:
        return geocoder.search(q, language, lat, lon, suggest)
    except SearchError as error:
        raise HTTPException(429 if error.code == "search_rate_limit" else 502, error.code) from error
    except ValueError as error:
        raise HTTPException(422, "invalid_search_query") from error


def sample_frames(location):
    manifest = ROOT / "samples" / "episode.json"
    if not manifest.exists():
        raise HTTPException(404, "sample_unavailable")
    from .radar import grid
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if any(abs(getattr(location, key)-metadata["location"][key]) > 0.001 for key in ("lat", "lon", "radius_km")):
        raise HTTPException(422, "sample_location_mismatch")
    _, affine, crs = grid(location)
    sample_path = ROOT / "samples" / "episode.npz"
    import hashlib
    if hashlib.sha256(sample_path.read_bytes()).hexdigest() != metadata.get("sha256"):
        raise ValueError("Sample checksum mismatch")

    def auxiliary_time(item, kind):
        if item.get(f"{kind}_time"):
            return datetime.fromisoformat(item[f"{kind}_time"])
        match = re.search(r"(\d{8}-\d{6})\.grib2", item.get(f"{kind}_source") or "")
        return datetime.strptime(match[1], "%Y%m%d-%H%M%S").replace(tzinfo=UTC) if match else None

    with np.load(sample_path, allow_pickle=False) as data:
        return [Frame(datetime.fromisoformat(item["time"]), data[f"rate_{i}"].copy(), affine, crs, item["source"],
                      data[f"reflectivity_{i}"].copy() if f"reflectivity_{i}" in data else None,
                      data[f"quality_{i}"].copy() if f"quality_{i}" in data else None,
                      item.get("reflectivity_source"), item.get("quality_source"),
                      auxiliary_time(item, "reflectivity"), auxiliary_time(item, "quality"),
                      data[f"composite_{i}"].copy() if f"composite_{i}" in data else None,
                      auxiliary_time(item, "composite_reflectivity"), item.get("composite_reflectivity_source"))
                for i, item in enumerate(metadata["frames"])]


@app.get("/api/sample")
def sample_info():
    path = ROOT / "samples" / "episode.json"
    if not path.exists():
        raise HTTPException(404, "sample_unavailable")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/replay")
def replay(request: ReplayRequest):
    location = Location(**request.model_dump(include={"lat", "lon", "radius_km", "threshold"}))
    with lock:
        try:
            frames = sample_frames(location) if request.sample else provider.frames(location, request.start, request.end)
            frames = [frame for frame in frames if request.start <= frame.time <= request.end]
        except (ProviderError, ValueError, OSError) as error:
            raise HTTPException(503, "provider_unavailable") from error
        if len(frames) < 2:
            raise HTTPException(404, "insufficient_observations")
        try:
            result = evaluate(frames, location)
        except ValueError as error:
            raise HTTPException(503, "invalid_observations") from error
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        result.update({"run_id": run_id, "location": location.model_dump(),
                       "start": request.start.isoformat(), "end": request.end.isoformat()})
        runs = CACHE / "runs"
        runs.mkdir(exist_ok=True)
        (runs / f"{run_id}.json").write_text(json.dumps({k: v for k, v in result.items() if k != "steps"}), encoding="utf-8")
        for old in sorted(runs.glob("*.json"))[:-50]:
            old.unlink()
        return result


@app.get("/api/runs")
def runs():
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted((CACHE/"runs").glob("*.json"), reverse=True)]


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
