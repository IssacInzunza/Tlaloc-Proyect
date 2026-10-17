from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.models import Location
from app.radar import Frame, coverage, grid, render
from pyproj import Geod


def frame(location=None, value=0):
    location = location or Location(lat=32.65, lon=-115.45)
    size, affine, crs = grid(location)
    return Frame(datetime.now(UTC), np.full((size, size), value, dtype="float32"), affine, crs, "test")


def test_georeferenced_distance_and_radius():
    location = Location(lat=32.65, lon=-115.45)
    observation = frame(location)
    lat, lon = observation.to_geo(50000, 0)
    _, _, distance = Geod(ellps="WGS84").inv(location.lon, location.lat, lon, lat)
    assert distance == pytest.approx(50000, abs=1)
    assert observation.spacing == 1000
    assert frame(Location(lat=32.65, lon=-115.45, radius_km=100)).rate.shape[0] > observation.rate.shape[0]


def test_no_data_is_not_dry():
    location = Location(lat=32, lon=-115)
    assert coverage(frame(location, np.nan), location).status == "insufficient_coverage"
    assert coverage(frame(location, 0), location).status == "no_precipitation_detected"


def test_partial_and_target_missing():
    location = Location(lat=32, lon=-115)
    observation = frame(location, 1)
    observation.rate[:, :45] = np.nan
    assert coverage(observation, location).status == "partial_coverage"
    center = observation.rate.shape[0]//2
    observation.rate[center, center] = np.nan
    assert coverage(observation, location).status == "insufficient_coverage"


def test_stale_observations_suppress_even_dry():
    location = Location(lat=32, lon=-115)
    observation = frame(location)
    observation.time -= timedelta(minutes=11)
    assert coverage(observation, location).status == "stale_observations"


@pytest.mark.parametrize(("quality", "status", "code"), [
    (0.1, "insufficient_coverage", "radar_quality_limited"),
    (0.5, "partial_coverage", "radar_quality_limited"),
    (1.0, "available", "radar_quality_good"),
])
def test_rqi_gates_surface_quality(quality, status, code):
    location = Location(lat=32, lon=-115)
    observation = frame(location, 1)
    observation.quality = np.full_like(observation.rate, quality)
    state = coverage(observation, location)
    assert state.status == status
    assert state.quality == code


def test_render_geographic_png_and_invalid_masks():
    location = Location(lat=32, lon=-115)
    observation = frame(location)
    observation.rate[0, 0] = np.nan
    rendered = render(observation, location)
    assert rendered["image"].startswith("data:image/png;base64,iVBOR")
    assert rendered["bounds"][0][0] < rendered["bounds"][1][0]
    assert rendered["bounds"][0][1] < rendered["bounds"][1][1]
    with pytest.raises(ValueError):
        Frame(datetime.now(), observation.rate, observation.transform, observation.crs, "test")
    with pytest.raises(ValueError):
        frame(location, -3)
