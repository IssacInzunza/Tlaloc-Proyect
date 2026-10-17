"""Prefix-only hindcasts; sampled radar target verification, not ground-truth rain."""
import time
from itertools import pairwise

import numpy as np
from pyproj import Geod

from .models import Location
from .nowcasting import predict
from .radar import Frame, coverage, render
from .tracking import track

# MRMS normally arrives every two minutes. Larger gaps cannot establish onset.
MAX_VERIFICATION_GAP_MINUTES = 5


def evaluate(frames: list[Frame], location: Location, include_images=True):
    started = time.perf_counter()
    if any(a.time >= b.time for a, b in pairwise(frames)):
        raise ValueError("Replay frames must have strictly increasing timestamps")
    steps, forecasts = [], []
    for index, frame in enumerate(frames):
        # Never expose a later frame to prediction, including during validation.
        predictions = predict(frames[:index + 1], location, now=frame.time)
        forecasts.append(predictions)
        step = {"time": frame.time.isoformat(),
                "predictions": [p.model_dump(mode="json") for p in predictions],
                "coverage": coverage(frame, location, frame.time).model_dump()}
        if include_images:
            step["frame"] = render(frame, location, frame.time)
        steps.append(step)

    times = [(frame.time - frames[0].time).total_seconds() / 60 for frame in frames]
    target = [float(frame.rate[tuple(size // 2 for size in frame.rate.shape)]) for frame in frames]
    known = [bool(np.isfinite(value)) for value in target]
    wet = [valid and value >= location.threshold for valid, value in zip(known, target)]
    gaps = [times[i] - times[i - 1] for i in range(1, len(times))]
    onsets = [i for i in range(1, len(frames)) if known[i - 1] and known[i]
              and not wet[i - 1] and wet[i] and gaps[i - 1] <= MAX_VERIFICATION_GAP_MINUTES]

    errors, leads, trajectory_errors = [], [], []
    false_alarms = hits = censored = ongoing = unknown_origin = 0
    alerted_onsets = set()
    geod = Geod(ellps="WGS84")
    for index, predictions in enumerate(forecasts):
        # Identical tracking history plus next observation; ambiguous matches lack a score.
        following = None
        if index + 1 < len(frames) and gaps[index] <= MAX_VERIFICATION_GAP_MINUTES:
            following = track(frames[:index + 2], location.threshold)
        for prediction in predictions:
            if following is not None and prediction.speed_kmh is not None and prediction.direction_deg is not None:
                actual = next((r for r in following if r.id == prediction.id and r.vx is not None
                               and r.vy is not None), None)
                if actual is not None:
                    lon, lat, _ = geod.fwd(prediction.lon, prediction.lat, prediction.direction_deg,
                                          prediction.speed_kmh / 3.6 * gaps[index] * 60)
                    actual_lat, actual_lon = frames[index + 1].to_geo(actual.x, actual.y)
                    _, _, distance = geod.inv(lon, lat, actual_lon, actual_lat)
                    trajectory_errors.append(distance / 1000)
            if prediction.arrival_minutes is None:
                continue
            if not known[index]:
                unknown_origin += 1
                continue
            if wet[index]:
                ongoing += 1
                continue
            lower, upper = prediction.arrival_minutes
            if not np.isfinite([lower, upper]).all() or not 0 <= lower <= upper <= 60:
                raise ValueError("Invalid forecast arrival interval")
            # Include first sample at/after horizon; never assume a gap was dry.
            end = next((j for j in range(index + 1, len(frames)) if times[j] - times[index] >= upper), None)
            limit = end if end is not None else len(frames) - 1
            future = list(range(index + 1, limit + 1))
            first_wet = next((j for j in future if wet[j]), None)
            # Once arrival has been observed, later coverage cannot erase it.
            evidence = [j for j in future if first_wet is None or j <= first_wet]
            contiguous = all(known[j] and times[j] - times[j - 1] <= MAX_VERIFICATION_GAP_MINUTES
                             for j in evidence)
            if not contiguous:
                censored += 1
                continue
            if first_wet is not None:
                # Onset lies between previous dry and first wet observation.
                observed_lower = times[first_wet - 1] - times[index]
                observed_upper = times[first_wet] - times[index]
                if observed_upper >= lower and observed_lower <= upper:
                    hits += 1
                    midpoint = (observed_lower + observed_upper) / 2
                    errors.append(abs((lower + upper) / 2 - midpoint))
                    leads.append(midpoint)
                    alerted_onsets.add(first_wet)
                elif end is not None:
                    false_alarms += 1
                else:
                    censored += 1
            elif end is None:
                censored += 1
            else:
                false_alarms += 1

    metrics = {
        "arrival_mae_minutes": float(np.mean(errors)) if errors else None,
        "false_alarm_forecasts": false_alarms, "hit_forecasts": hits,
        "missed_onsets": sum(i not in alerted_onsets for i in onsets),
        "censored_forecasts": censored, "observed_onsets": len(onsets),
        "ongoing_rain_forecasts": ongoing, "unknown_target_forecasts": unknown_origin,
        "mean_lead_minutes": float(np.mean(leads)) if leads else None,
        "trajectory_mae_km": float(np.mean(trajectory_errors)) if trajectory_errors else None,
        "trajectory_samples": len(trajectory_errors),
        "target_data_availability": float(np.mean(known)) if known else None,
        "verification_gap_count": sum(gap > MAX_VERIFICATION_GAP_MINUTES for gap in gaps),
        "processing_seconds": time.perf_counter() - started,
    }
    return {"steps": steps, "metrics": metrics, "frame_count": len(frames), "experimental": True}
