"""Synthetic fixtures are isolated tests, never application/provider data."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from app import replay
from app.models import Location, Prediction
from app.radar import Frame
from pyproj import CRS
from rasterio.transform import from_origin

LOCATION = Location(lat=32, lon=-116, radius_km=10)
START = datetime(2025, 1, 1, tzinfo=UTC)
CRS_LOCAL = CRS.from_proj4("+proj=aeqd +lat_0=32 +lon_0=-116 +datum=WGS84 +units=m")


def frames(minutes, values):
    return [Frame(START + timedelta(minutes=minute), np.full((25, 25), value, dtype="float32"),
                  from_origin(-12500, 12500, 1000, 1000), CRS_LOCAL, "test-only")
            for minute, value in zip(minutes, values)]


def prediction(frame, arrival=(1, 3), identity="echo", **kwargs):
    return Prediction(id=identity, intensity="light", peak_rate=1, area_km2=3,
                      distance_km=1, lat=32, lon=-116, observation_time=frame.time,
                      data_quality="test-only", arrival_minutes=list(arrival) if arrival else None,
                      **kwargs)


def run(monkeypatch, observations, arrivals):
    monkeypatch.setattr(replay, "predict", lambda past, location, now: [
        prediction(past[-1], arrival, identity=str(i))
        for i, arrival in enumerate(arrivals.get(past[-1].time, []))])
    monkeypatch.setattr(replay, "track", lambda *args: [])
    return replay.evaluate(observations, LOCATION, include_images=False)["metrics"]


def test_prediction_sees_only_chronological_prefix_and_actual_time(monkeypatch):
    observations = frames([0, 2, 4, 6, 8, 10, 12, 15], [0] * 8)
    seen = []

    def predict(past, location, now):
        index = len(seen)
        assert len(past) == index + 1
        assert all(a is b for a, b in zip(past, observations[:index + 1]))
        assert now == observations[index].time
        seen.append(now)
        return []

    def validate(past, threshold):
        assert len(seen) == len(observations)  # Validation only after all predictions.
        return []

    monkeypatch.setattr(replay, "predict", predict)
    monkeypatch.setattr(replay, "track", validate)
    result = replay.evaluate(observations, LOCATION, include_images=False)
    assert len(seen) == len(observations)
    assert result["frame_count"] == 8
    assert "frame" not in result["steps"][0]


@pytest.mark.parametrize("minutes", [[0, 0], [2, 0]])
def test_duplicate_or_reversed_timestamps_rejected(monkeypatch, minutes):
    monkeypatch.setattr(replay, "predict", lambda *args, **kwargs: pytest.fail("prediction called"))
    with pytest.raises(ValueError, match="strictly increasing"):
        replay.evaluate(frames(minutes, [0, 0]), LOCATION, False)


def test_sampled_onset_hit_uses_bracket_midpoint(monkeypatch):
    observations = frames([0, 2, 4], [0, 0, 1])
    result = run(monkeypatch, observations, {START: [(2, 4)]})
    assert result["hit_forecasts"] == 1
    assert result["observed_onsets"] == 1
    assert result["missed_onsets"] == 0
    assert result["arrival_mae_minutes"] == 0
    assert result["mean_lead_minutes"] == 3
    assert result["target_data_availability"] == 1


def test_all_regions_scored_and_no_invented_four_minute_tolerance(monkeypatch):
    observations = frames([0, 2, 4, 6, 8], [0, 0, 0, 0, 1])
    result = run(monkeypatch, observations, {START: [(1, 3), (6, 8)]})
    assert result["hit_forecasts"] == 1
    assert result["false_alarm_forecasts"] == 1
    assert result["mean_lead_minutes"] == 7


@pytest.mark.parametrize("minutes,values,interval", [
    ([0, 2], [0, 0], (2, 4)),  # Replay ends before the full horizon.
    ([0, 2, 4], [0, np.nan, 0], (1, 4)),
    ([0, 8], [0, 0], (1, 4)),  # Endpoint alone cannot establish absence.
    ([0, 8], [0, 1], (1, 4)),  # Nor arrival across a large gap.
])
def test_incomplete_unknown_and_gapped_verification_censored(monkeypatch, minutes, values, interval):
    observations = frames(minutes, values)
    result = run(monkeypatch, observations, {START: [interval]})
    assert result["censored_forecasts"] == 1
    assert result["hit_forecasts"] == result["false_alarm_forecasts"] == 0
    assert result["arrival_mae_minutes"] is None
    assert result["mean_lead_minutes"] is None


def test_full_dry_horizon_false_alarm(monkeypatch):
    observations = frames([0, 2, 4], [0, 0, 0])
    result = run(monkeypatch, observations, {START: [(1, 4)]})
    assert result["false_alarm_forecasts"] == 1
    assert result["censored_forecasts"] == 0


def test_later_missing_coverage_does_not_erase_observed_hit(monkeypatch):
    observations = frames([0, 2, 4, 6], [0, 1, np.nan, 0])
    result = run(monkeypatch, observations, {START: [(0, 6)]})
    assert result["hit_forecasts"] == 1
    assert result["censored_forecasts"] == 0


def test_observed_hit_does_not_need_remaining_horizon(monkeypatch):
    observations = frames([0, 2], [0, 1])
    result = run(monkeypatch, observations, {START: [(1, 10)]})
    assert result["hit_forecasts"] == 1
    assert result["censored_forecasts"] == 0


def test_onset_without_prior_alert_is_missed(monkeypatch):
    result = run(monkeypatch, frames([0, 2], [0, 1]), {})
    assert result["observed_onsets"] == result["missed_onsets"] == 1


def test_unknown_to_wet_and_long_gap_are_not_known_onsets(monkeypatch):
    result = run(monkeypatch, frames([0, 2, 10, 12], [np.nan, 1, 0, 1]), {})
    assert result["observed_onsets"] == 1
    assert result["target_data_availability"] == 0.75
    assert result["verification_gap_count"] == 1


def test_existing_wet_and_unknown_origins_are_not_successful_arrivals(monkeypatch):
    observations = frames([0, 2, 4], [1, np.nan, 1])
    result = run(monkeypatch, observations, {START: [(0, 3)], START + timedelta(minutes=2): [(0, 3)]})
    assert result["ongoing_rain_forecasts"] == 1
    assert result["unknown_target_forecasts"] == 1
    assert result["hit_forecasts"] == 0
    assert result["observed_onsets"] == 0


def test_empty_data_metrics_are_nullable(monkeypatch):
    result = run(monkeypatch, [], {})
    assert result["target_data_availability"] is None
    assert result["trajectory_mae_km"] is None
    assert result["arrival_mae_minutes"] is None
    assert result["processing_seconds"] >= 0


def test_trajectory_uses_associated_next_frame_and_actual_elapsed_time(monkeypatch):
    observations = frames([0, 3], [0, 0])
    lon, lat, _ = replay.Geod(ellps="WGS84").fwd(-116, 32, 90, 3000)
    actual_x, actual_y = __import__("pyproj").Transformer.from_crs(
        "EPSG:4326", CRS_LOCAL, always_xy=True).transform(lon, lat)
    monkeypatch.setattr(replay, "predict", lambda past, location, now: [
        prediction(past[-1], None, speed_kmh=60, direction_deg=90)] if len(past) == 1 else [])
    monkeypatch.setattr(replay, "track", lambda past, threshold: [
        SimpleNamespace(id="echo", x=actual_x, y=actual_y, vx=1, vy=0)])
    result = replay.evaluate(observations, LOCATION, False)["metrics"]
    assert result["trajectory_samples"] == 1
    assert result["trajectory_mae_km"] == pytest.approx(0, abs=1e-7)


def test_unassociated_trajectory_is_nullable(monkeypatch):
    result = run(monkeypatch, frames([0, 2], [0, 0]), {START: [(1, 2)]})
    assert result["trajectory_samples"] == 0
    assert result["trajectory_mae_km"] is None
