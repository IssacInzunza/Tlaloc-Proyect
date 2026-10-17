"""Scientific invariants for distinct precipitation-rate and radar-echo layers.

Fixtures are synthetic and verify rendering semantics, not meteorological skill.
"""
import base64
import io
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.models import Location
from app.nowcasting import predict
from app.radar import Frame, coverage, grid, render
from app.tracking import segment
from PIL import Image


def observation(rate=0.0, reflectivity=None):
    location = Location(lat=32.5862, lon=-115.4341, radius_km=50)
    size, transform, crs = grid(location)
    frame = Frame(
        datetime(2026, 10, 17, 19, 22, tzinfo=UTC),
        np.full((size, size), rate, dtype="float32"),
        transform,
        crs,
        "https://example.invalid/precip-rate.grib2.gz",
        None if reflectivity is None else np.full((size, size), reflectivity, dtype="float32"),
    )
    frame.reflectivity_source = "https://example.invalid/reflectivity.grib2.gz"
    return location, frame


def pixels(layer):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(layer["image"].split(",", 1)[1]))))


def test_radar_echo_does_not_become_surface_rain():
    location, frame = observation(rate=0, reflectivity=25)
    rendered = render(frame, location)
    rate, echo = rendered["layers"]["rate"], rendered["layers"]["reflectivity"]
    center = tuple(s // 2 for s in frame.rate.shape)

    assert rate["unit"] == "mm/h"
    assert echo["unit"] == "dBZ"
    assert rate["max_value"] == 0
    assert echo["max_value"] == 25
    assert rate["echo_pixels"] == 0
    assert echo["echo_pixels"] > 0
    assert pixels(rate)[center][3] == 0
    assert pixels(echo)[center][3] > 0
    assert np.all(frame.rate == 0)
    assert coverage(frame, location, frame.time).status == "no_precipitation_detected"
    assert predict([frame], location, frame.time) == []


@pytest.mark.parametrize("layer", ["rate", "reflectivity"])
def test_missing_data_and_valid_below_threshold_are_distinct(layer):
    location, frame = observation(rate=0, reflectivity=0)
    missing_frame = observation(rate=np.nan, reflectivity=np.nan)[1]
    missing = render(missing_frame, location)["layers"][layer]
    dry = render(frame, location)["layers"][layer]
    center = tuple(s // 2 for s in frame.rate.shape)

    assert missing["valid_fraction"] == 0
    assert dry["valid_fraction"] == 1
    assert missing["echo_pixels"] == dry["echo_pixels"] == 0
    assert missing["max_value"] is None
    assert dry["max_value"] == 0
    assert pixels(missing)[center][3] > 0
    assert pixels(dry)[center][3] == 0


def test_absent_reflectivity_is_not_synthesized_from_rate():
    location, frame = observation(rate=10)
    layers = render(frame, location)["layers"]
    assert "reflectivity" not in layers
    assert layers["rate"]["echo_pixels"] > 0


def test_layers_retain_product_provenance_and_legacy_rate_overlay():
    location, frame = observation(rate=2, reflectivity=35)
    frame.reflectivity_time = frame.time + timedelta(seconds=30)
    rendered = render(frame, location)
    rate, echo = rendered["layers"]["rate"], rendered["layers"]["reflectivity"]
    assert rate["source"] == frame.source
    assert echo["source"] == frame.reflectivity_source
    assert rate["time"] == frame.time.isoformat()
    assert echo["time"] == frame.reflectivity_time.isoformat()
    assert rate["bounds"] == echo["bounds"] == rendered["bounds"]
    assert rate["image"] == rendered["image"]
    assert rate["valid_fraction"] == echo["valid_fraction"] == 1


def test_statistics_use_native_grid_without_counting_missing_as_no_echo():
    location, frame = observation(rate=0, reflectivity=0)
    frame.rate[:20, :] = np.nan
    frame.reflectivity[:10, :] = np.nan
    frame.rate[40:50, 40:50] = 0.1
    frame.reflectivity[40:50, 40:50] = 5
    layers = render(frame, location)["layers"]
    rate, echo = layers["rate"], layers["reflectivity"]
    assert rate["valid_fraction"] == pytest.approx(float(np.isfinite(frame.rate).mean()), abs=0.0001)
    assert echo["valid_fraction"] == pytest.approx(float(np.isfinite(frame.reflectivity).mean()), abs=0.0001)
    assert rate["echo_pixels"] == echo["echo_pixels"] == 100
    assert rate["max_value"] == pytest.approx(0.1)
    assert echo["max_value"] == 5


def test_northeast_echo_is_rendered_at_geographic_position():
    location, frame = observation(rate=0, reflectivity=0)
    x, y = frame.xy()
    # A small synthetic echo northeast of the marker catches axis/latitude flips.
    frame.reflectivity[(abs(x - 12000) < 3000) & (abs(y - 8000) < 3000)] = 30
    echo = render(frame, location)["layers"]["reflectivity"]
    rgba = pixels(echo)
    rows, cols = np.where(rgba[:, :, 3] > 100)
    assert rows.size > 0
    (south, west), (north, east) = echo["bounds"]
    measured_lon = west + (cols.mean() + 0.5) / rgba.shape[1] * (east - west)
    measured_lat = north - (rows.mean() + 0.5) / rgba.shape[0] * (north - south)
    expected_lat, expected_lon = frame.to_geo(12000, 8000)
    assert measured_lat == pytest.approx(expected_lat, abs=0.015)
    assert measured_lon == pytest.approx(expected_lon, abs=0.015)


@pytest.mark.parametrize("offset_seconds", [-30, 0, 30])
def test_segmentation_does_not_use_future_low_altitude_reflectivity(offset_seconds):
    _, frame = observation(rate=2, reflectivity=35)
    frame.reflectivity_time = frame.time + timedelta(seconds=offset_seconds)
    regions = segment(frame)
    assert regions
    expected = None if offset_seconds > 0 else 35
    assert all(region.reflectivity == expected for region in regions)


@pytest.mark.parametrize(
    ("quality", "eventual_status", "eventual_quality"),
    [(0.1, "insufficient_coverage", "radar_quality_limited"),
     (1.0, "available", "radar_quality_good")],
)
def test_quality_is_available_only_at_or_after_its_observation_time(
    quality, eventual_status, eventual_quality
):
    location, frame = observation(rate=2)
    frame.quality = np.full_like(frame.rate, quality)
    frame.quality_time = frame.time + timedelta(seconds=30)
    before = coverage(frame, location, frame.time)
    assert before.status == "available"
    assert before.quality == "product_mask_only"
    at_observation = coverage(frame, location, frame.quality_time)
    assert at_observation.status == eventual_status
    assert at_observation.quality == eventual_quality
