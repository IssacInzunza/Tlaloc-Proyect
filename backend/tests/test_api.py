from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app import main
from app.checkpoints import TrackingStore
from app.history import AlertHistory
from app.models import Location, Prediction
from app.providers import ProviderError
from app.radar import Frame, grid
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "history", AlertHistory(tmp_path/"history.sqlite3"))
    monkeypatch.setattr(main, "tracking_store", TrackingStore(tmp_path / "tracking"))
    main.result_cache.clear()
    main.tracking_cache.clear()
    location = Location(lat=32, lon=-115)
    size, affine, crs = grid(location)
    observation = Frame(datetime.now(UTC), np.zeros((size, size), dtype="float32"), affine, crs, "test")
    monkeypatch.setattr(main.provider, "frames", lambda *_args, **_kwargs: [observation])
    return TestClient(main.app)


def test_health_and_real_analysis_contract(client):
    assert client.get("/api/health").json()["version"] == "1.0.0"
    result = client.get("/api/analysis", params={"lat": 32, "lon": -115})
    assert result.status_code == 200
    body = result.json()
    assert body["unit"] == "mm/h"
    assert body["target_rate"] == 0
    assert body["coverage"]["status"] == "no_precipitation_detected"
    assert body["predictions"] == []
    assert len(body["frames"]) == 1


def test_address_search_requires_consent_before_upstream_contact(client, monkeypatch):
    def never_called(*_args, **_kwargs):
        pytest.fail("Address text sent externally without explicit consent")
    monkeypatch.setattr(main.geocoder, "search", never_called)
    assert client.get("/api/search", params={"q": "example street"}).status_code == 403


def test_consented_address_search_uses_separate_geocoder(client, monkeypatch):
    called = []
    monkeypatch.setattr(main.geocoder, "search", lambda *args: called.append(args) or
                        [{"name": "Example street", "lat": 32, "lon": -115, "provider": "Photon"}])
    response = client.get("/api/search", params={"q": "example street", "lat": 32,
                          "lon": -115, "language": "es", "suggest": True, "external": True})
    assert response.status_code == 200
    assert called == [("example street", "es", 32, -115, True)]


@pytest.mark.parametrize("params", [
    {"lat": 91, "lon": 0}, {"lat": 0, "lon": 181}, {"lat": "nan", "lon": 0},
    {"lat": 0, "lon": 0, "radius_km": 101}, {"lat": 0, "lon": 0, "radius_km": 9},
    {"lat": 0, "lon": 0, "threshold": 0}, {"lat": 0},
])
def test_invalid_queries_cannot_trigger_downloads(client, params, monkeypatch):
    def never_called(*_args, **_kwargs):
        pytest.fail("Invalid request triggered a radar download")
    monkeypatch.setattr(main.provider, "frames", never_called)
    assert client.get("/api/analysis", params=params).status_code == 422


def test_provider_failure_is_explicit(client, monkeypatch):
    def failed(*_args):
        raise ProviderError("offline")
    monkeypatch.setattr(main.provider, "frames", failed)
    result = client.get("/api/analysis", params={"lat": 32, "lon": -115}).json()
    assert result["coverage"]["status"] == "provider_unavailable"
    assert result["target_rate"] is None
    assert result["predictions"] == [] and result["frames"] == []


def test_cache_scoped_by_location_and_radius(client, monkeypatch):
    calls = []
    def empty(location):
        calls.append(location)
        return []
    monkeypatch.setattr(main.provider, "frames", empty)
    for params in [{"lat": 32, "lon": -115}, {"lat": 32, "lon": -115},
                   {"lat": 33, "lon": -115}, {"lat": 33, "lon": -115, "radius_km": 60}]:
        assert client.get("/api/analysis", params=params).status_code == 200
    assert len(calls) == 3


def test_cached_observation_is_rechecked_for_staleness(client, monkeypatch):
    location = Location(lat=32, lon=-115)
    size, affine, crs = grid(location)
    observation = Frame(datetime.now(UTC)-timedelta(minutes=9),
                        np.zeros((size, size), dtype="float32"), affine, crs, "test")
    calls = []
    monkeypatch.setattr(main.provider, "frames", lambda *_args: calls.append(1) or [observation])
    first = client.get("/api/analysis", params={"lat": 32, "lon": -115}).json()
    assert first["coverage"]["status"] == "no_precipitation_detected"
    observation.time -= timedelta(minutes=2)
    second = client.get("/api/analysis", params={"lat": 32, "lon": -115}).json()
    assert second["coverage"]["status"] == "stale_observations"
    assert second["predictions"] == []
    assert len(calls) == 1


@pytest.mark.parametrize("overrides", [
    {"end": "2020-01-01T03:00:00Z"}, {"start": "2020-01-01T00:00:00"},
    {"end": "2020-01-01T00:00:30Z"}, {"end": "2099-01-01T00:10:00Z"},
])
def test_replay_bounds(client, overrides):
    body = {"lat": 32, "lon": -115, "start": "2020-01-01T00:00:00Z", "end": "2020-01-01T00:10:00Z"}
    body.update(overrides)
    assert client.post("/api/replay", json=body).status_code == 422


def test_history_dedup_update_cancel_and_location_isolation(tmp_path):
    history = AlertHistory(tmp_path/"alerts.sqlite3")
    location = Location(lat=32, lon=-115)
    alert = Prediction(id="cell", intensity="moderate", peak_rate=3, area_km2=5,
                       distance_km=10, lat=32.1, lon=-115, observation_time=datetime.now(UTC),
                       data_quality="product_mask_only")
    history.update(location, [alert], "2020-01-01T00:00:00Z")
    history.update(location, [alert], "2020-01-01T00:00:00Z")
    assert len(history.list(location)) == 1
    alert.level = "preventive"
    history.update(location, [alert], "2020-01-01T00:02:00Z")
    assert history.list(location)[0]["action"] == "updated"
    history.update(location, [], "2020-01-01T00:04:00Z")
    assert history.list(location)[0]["action"] == "cancelled"
    assert not history.list(Location(lat=33, lon=-115))
    assert not history.list(Location(lat=32, lon=-115, radius_km=60))


def test_history_outage_suspends_instead_of_claiming_rain_stopped(tmp_path):
    history = AlertHistory(tmp_path/"alerts.sqlite3")
    location = Location(lat=32, lon=-115)
    alert = Prediction(id="cell", intensity="light", peak_rate=1, area_km2=5, distance_km=1,
                       lat=32, lon=-115, observation_time=datetime.now(UTC), data_quality="unknown")
    history.update(location, [alert], "2020-01-01T00:00:00Z")
    history.suspend(location)
    assert history.list(location)[0]["action"] == "suspended"
