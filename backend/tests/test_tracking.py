"""Deterministic geometry and lifecycle checks; synthetic data is test-only."""
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pytest
from pyproj import CRS
from rasterio.transform import from_origin

from backend.app.models import Location
from backend.app.nowcasting import arrival, predict
from backend.app.radar import Frame
from backend.app.tracking import associate, segment, track

START = datetime(2026, 1, 1, tzinfo=UTC)
LOCATION = Location(lat=32, lon=-117)
CRS_LOCAL = CRS.from_proj4("+proj=aeqd +lat_0=32 +lon_0=-117 +datum=WGS84 +units=m")


def frame(seconds=0, boxes=((48, 53, 28, 33),), rate=3):
    values = np.zeros((101, 101), dtype=np.float32)
    for r0, r1, c0, c1 in boxes:
        values[r0:r1, c0:c1] = rate
    result = Frame(START+timedelta(seconds=seconds), values,
                   from_origin(-50500, 50500, 1000, 1000), CRS_LOCAL, "test-only")
    result.quality = np.ones_like(values)
    return result


def approaching():
    return [frame(i*120, ((48, 53, 28+2*i, 33+2*i),)) for i in range(3)]


def test_approaching_real_timestamps_units_and_stable_identity():
    frames = approaching()
    region = track(frames)[0]
    assert region.age == 3 and region.confidence == "high"
    assert region.id == segment(frames[0])[0].id
    assert region.vx == pytest.approx(2000/120)
    assert region.vy == 0
    prediction = predict(frames, LOCATION, frames[-1].time)[0]
    assert prediction.speed_kmh == 60 and prediction.direction_deg == 90
    # Leading edge x=-13.5 km, centroid x=-16 km: arrival uses footprint.
    assert arrival(region, frames[-1]) == pytest.approx(13.5)
    assert prediction.arrival_minutes[0] < 13.5 < prediction.arrival_minutes[1]


@pytest.mark.parametrize("boxes", [
    [((48, 53, 32-2*i, 37-2*i),) for i in range(3)],  # away
    [((38, 43, 28+2*i, 33+2*i),) for i in range(3)],  # lateral
    [((48, 53, 28, 33),) for _ in range(3)],  # stationary
])
def test_no_arrival_for_away_lateral_or_stationary(boxes):
    frames = [frame(i*120, box) for i, box in enumerate(boxes)]
    region = track(frames)[0]
    assert region.vx is not None
    assert arrival(region, frames[-1]) is None
    assert predict(frames, LOCATION, frames[-1].time)[0].arrival_minutes is None


def test_square_pixels_do_not_enlarge_lateral_footprint():
    latest = frame(boxes=((51, 53, 40, 43),))
    region = segment(latest)[0]
    region.vx, region.vy = 10.0, 0.0
    assert arrival(region, latest) is None


def test_stationary_rain_at_target_has_zero_arrival():
    latest = frame(boxes=((49, 52, 49, 52),))
    region = segment(latest)[0]
    region.vx = region.vy = 0
    assert arrival(region, latest) == 0


@pytest.mark.parametrize("rate,event", [(6, "intensifying"), (1, "weakening")])
def test_intensity_changes_are_not_translation(rate, event):
    frames = [frame(), frame(120, rate=rate)]
    region = track(frames)[0]
    assert region.event == event
    assert region.vx == 0 and region.vy == 0


def test_new_echo_and_no_rain():
    dry, wet = frame(boxes=()), frame(120)
    region = track([dry, wet])[0]
    assert region.event == "new_echo" and region.vx is None
    assert predict([dry], LOCATION, dry.time) == []


@pytest.mark.parametrize("seconds", [0, -120, 601])
def test_duplicate_reversed_and_long_gap_reject_motion(seconds):
    region = track([frame(), frame(seconds)])[0]
    assert region.event == "gap_uncertain" and region.vx is None


def test_registration_failure_never_implies_stationarity(monkeypatch):
    monkeypatch.setattr(cv2, "phaseCorrelate", lambda a, b: ((0, 0), 0.01))
    region = track(approaching())[0]
    assert region.event == "motion_uncertain"
    assert region.vx is None and region.confidence == "low"


def test_split_and_merge_with_ambiguous_parentage(monkeypatch):
    # Isolate component lineage from phase registration of a deforming echo.
    monkeypatch.setattr(cv2, "phaseCorrelate", lambda a, b: ((0, 0), 0.9))
    joined = ((45, 56, 28, 39),)
    split = ((45, 49, 28, 39), (52, 56, 28, 39))
    children = track([frame(boxes=joined), frame(120, boxes=split)])
    assert len(children) == 2
    assert all(r.event == "split_uncertain" and r.vx is None for r in children)
    merged = track([frame(boxes=split), frame(120, boxes=joined)])[0]
    assert merged.event == "merge_uncertain" and merged.vx is None


def test_boundary_and_missing_coverage_cannot_assert_new_echo():
    region = track([frame(boxes=()), frame(120, ((48, 53, 0, 5),))])[0]
    assert region.event == "coverage_uncertain"
    previous, current = frame(boxes=()), frame(120)
    previous.rate[48:53, 28:33] = np.nan
    region = track([previous, current])[0]
    assert region.event == "coverage_uncertain"


def test_age_adjusts_eta_and_degrades_confidence():
    frames = approaching()
    latest = frames[-1]
    region = track(frames)[0]
    assert arrival(region, latest, 120) == pytest.approx(arrival(region, latest)-2)
    fresh = predict(frames, LOCATION, latest.time)[0]
    aged = predict(frames, LOCATION, latest.time+timedelta(minutes=3))[0]
    assert fresh.confidence == "high" and aged.confidence == "medium"
    assert sum(aged.arrival_minutes) < sum(fresh.arrival_minutes)
    old = predict(frames, LOCATION, latest.time+timedelta(minutes=6))[0]
    assert old.confidence == "low" and old.arrival_minutes is None
    assert predict(frames, LOCATION, latest.time+timedelta(minutes=11)) == []
    assert predict(frames, LOCATION, latest.time-timedelta(seconds=1)) == []


def test_invalid_target_and_inadequate_coverage_stop_prediction():
    frames = approaching()
    frames[-1].rate[50, 50] = np.nan
    assert predict(frames, LOCATION, frames[-1].time) == []
    frames[-1].rate[:70, :] = np.nan
    assert predict(frames, LOCATION, frames[-1].time) == []


def test_warps_once_per_prior_component(monkeypatch):
    previous = frame(boxes=((40, 44, 28, 32), (55, 59, 28, 32)))
    current = frame(120, ((40, 44, 30, 34), (55, 59, 30, 34)))
    original, calls = cv2.warpAffine, []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(cv2, "warpAffine", counted)
    associate(previous, current, segment(previous), segment(current))
    assert len(calls) == 2


def test_same_shape_different_grid_cannot_be_associated():
    previous, current = frame(), frame(120)
    current.transform = from_origin(-49500, 50500, 1000, 1000)
    region = track([previous, current])[0]
    assert region.event == "gap_uncertain" and region.vx is None


def test_quality_is_required_for_high_confidence_and_low_rqi_blocks():
    frames = approaching()
    frames[-1].quality = None
    assert predict(frames, LOCATION, frames[-1].time)[0].confidence == "medium"
    frames[-1].quality = np.full_like(frames[-1].rate, 0.6)
    assert predict(frames, LOCATION, frames[-1].time)[0].confidence == "medium"
    frames[-1].quality[50, 50] = 0.1
    assert predict(frames, LOCATION, frames[-1].time) == []


def test_irregular_intervals_use_seconds_not_assumed_cadence():
    frames = [frame(0), frame(180, ((48, 53, 31, 36),)),
              frame(420, ((48, 53, 35, 40),))]
    region = track(frames)[0]
    assert region.vx == pytest.approx(1000/60)
    assert region.confidence == "high"


def test_long_horizon_arrival_has_no_precise_interval():
    latest = frame(boxes=((48, 53, 4, 9),))
    region = segment(latest)[0]
    region.vx, region.vy, region.confidence = 20.0, 0.0, "high"
    assert 30 < arrival(region, latest) < 60
    result = predict([latest], LOCATION, latest.time, tracked_regions=[region])[0]
    assert result.arrival_minutes is None
    assert result.confidence == "low" and result.level == "informational"


def test_stationary_motion_has_no_arrow_and_explains_arrival():
    frames = [frame(i*120) for i in range(3)]
    result = predict(frames, LOCATION, frames[-1].time)[0]
    assert result.speed_kmh == 0
    assert result.direction_deg is None and result.vector_end is None
    assert result.arrival_status == "stationary"


def test_arrival_reason_distinguishes_uncertain_lateral_and_low_confidence():
    unknown = frame()
    assert predict([unknown], LOCATION, unknown.time)[0].arrival_status == "motion_uncertain"
    frames = [frame(i*120, ((38, 43, 28+2*i, 33+2*i),)) for i in range(3)]
    assert predict(frames, LOCATION, frames[-1].time)[0].arrival_status == "no_intersection"
    frames = approaching()
    assert predict(frames, LOCATION, frames[-1].time)[0].arrival_status == "estimated"
    assert predict(frames, LOCATION, frames[-1].time+timedelta(minutes=6))[0].arrival_status == "low_confidence"


def test_tracking_checkpoint_survives_restart_and_rejects_stale_state(tmp_path):
    from backend.app.checkpoints import TrackingStore
    now = datetime.now(UTC)
    frames = approaching()
    for i, item in enumerate(frames):
        item.time = now-timedelta(seconds=(2-i)*120)
    regions = track(frames)
    store = TrackingStore(tmp_path)
    store.save("scope", frames[-1], regions)
    previous, restored = TrackingStore(tmp_path).load("scope")
    assert restored[0].id == regions[0].id
    assert restored[0].age == 3 and restored[0].vx == regions[0].vx
    next_frame = frame(0, ((48, 53, 34, 39),))
    next_frame.time = now+timedelta(seconds=120)
    continued = associate(previous, next_frame, restored, segment(next_frame))[0]
    assert continued.id == regions[0].id and continued.age == 4
    assert continued.confidence == "high"
    previous.time = now-timedelta(minutes=11)
    store.save("scope", previous, restored)
    assert store.load("scope") is None
    store.path("scope").write_bytes(b"damaged checkpoint")
    assert store.load("scope") is None
