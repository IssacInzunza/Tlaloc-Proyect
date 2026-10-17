"""Extrapolate the observed footprint, using actual timestamps and meter coordinates."""
from datetime import UTC, datetime

import cv2
import numpy as np

from .models import Location, Prediction
from .radar import Frame, coverage
from .tracking import Region, track


def arrival(region: Region, frame: Frame, elapsed_seconds=0) -> float | None:
    if region.vx is None or region.vy is None:
        return None
    x, y = frame.xy()
    px = x[region.mask] + region.vx*elapsed_seconds
    py = y[region.mask] + region.vy*elapsed_seconds
    # Intersect the target with each translated square pixel. Circumscribed disks
    # would predict hits for lateral cells whose actual footprint misses the target.
    half = frame.spacing / 2
    enter = np.zeros(px.shape, dtype=float)
    leave = np.full(px.shape, 3600.0)
    for position, velocity in ((px, region.vx), (py, region.vy)):
        if abs(velocity) < 1e-8:
            leave[np.abs(position) > half] = -1
        else:
            first, last = (-half-position)/velocity, (half-position)/velocity
            enter = np.maximum(enter, np.minimum(first, last))
            leave = np.minimum(leave, np.maximum(first, last))
    times = enter[enter <= leave] / 60
    return float(times.min()) if times.size else None


def predict(frames: list[Frame], location: Location, now: datetime | None = None,
            tracked_regions: list[Region] | None = None) -> list[Prediction]:
    if not frames:
        return []
    frame = frames[-1]
    now = now or datetime.now(UTC)
    if frame.time > now:
        return []
    state = coverage(frame, location, now)
    if state.status in ("stale_observations", "insufficient_coverage"):
        return []
    result = []
    elapsed = max(0, (now-frame.time).total_seconds())
    x, y = frame.xy()
    for region in (track(frames, location.threshold) if tracked_regions is None else tracked_regions):
        distance = float(np.hypot(x[region.mask], y[region.mask]).min())/1000
        if distance > location.radius_km:
            continue
        lat, lon = frame.to_geo(region.x, region.y)
        eta = arrival(region, frame, elapsed)
        interval, level = None, "informational"
        confidence = region.confidence
        if (state.status == "partial_coverage" or state.quality != "radar_quality_good") and confidence == "high":
            confidence = "medium"
        if elapsed > 300:
            confidence = "low"
        elif elapsed > 120 and confidence == "high":
            confidence = "medium"
        if eta is not None and eta > 30:
            confidence = "low"
        if eta is not None and confidence != "low":
            uncertainty = 3 + eta*0.25 + state.age_minutes*0.5
            interval = [round(max(0, eta-uncertainty), 1), round(min(60, eta+uncertainty), 1)]
            if eta <= 30:
                level = "preventive"
            if eta <= 10 and confidence == "high" and state.valid_fraction >= 0.95:
                level = "imminent"
        direction = speed = None
        vector_end = None
        if region.vx is not None:
            speed = round(float(np.hypot(region.vx, region.vy))*3.6, 1)
            if speed >= 1.8:
                direction = round(float(np.degrees(np.arctan2(region.vx, region.vy))) % 360, 1)
            end_lat, end_lon = frame.to_geo(region.x+region.vx*600, region.y+region.vy*600)
            vector_end = [end_lat, end_lon]
        contours, _ = cv2.findContours(region.mask.astype("uint8"), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        polygon = []
        if contours:
            contour = cv2.approxPolyDP(max(contours, key=cv2.contourArea), 1, True)
            for col, row in contour.reshape(-1, 2):
                plat, plon = frame.to_geo(float(x[row, col]), float(y[row, col]))
                polygon.append([plat, plon])
        result.append(Prediction(
            id=region.id, level=level, intensity="heavy" if region.peak >= 10 else
            "moderate" if region.peak >= 2 else "light", peak_rate=round(region.peak, 2),
            area_km2=region.area, distance_km=round(distance, 1), lat=lat, lon=lon,
            direction_deg=direction, speed_kmh=speed, arrival_minutes=interval,
            confidence=confidence, event=region.event, observation_time=frame.time,
            data_quality=state.quality, vector_end=vector_end, polygon=polygon,
        ))
    return sorted(result, key=lambda p: (p.arrival_minutes or [999])[0])
