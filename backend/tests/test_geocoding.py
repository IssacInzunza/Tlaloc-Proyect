"""Actual Photon response excerpts captured 2026-10-17; no invented addresses."""
import copy

import httpx
import pytest
from app.geocoding import Geocoder, SearchError

# Actual response for the reported query, lang=default, Mexicali bias.
# Retain OSM IDs so these excerpts are traceable to mapped features.
ACTUAL = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {
        "osm_type": "W", "osm_id": 757440405, "osm_key": "highway",
        "osm_value": "residential", "type": "street", "name": "Avenida de los Naranjos",
        "locality": "Fraccionamiento Los Pinos", "city": "Mexicali",
        "state": "Baja California", "country": "México", "countrycode": "MX"},
     "geometry": {"type": "Point", "coordinates": [-115.4498162, 32.6472072]}},
    {"type": "Feature", "properties": {
        "osm_type": "W", "osm_id": 52121086, "osm_key": "highway",
        "osm_value": "residential", "type": "street", "name": "Calle Naranjos",
        "city": "Mexicali", "state": "Baja California", "country": "México", "countrycode": "MX"},
     "geometry": {"type": "Point", "coordinates": [-115.4819467, 32.6537055]}}
]}


def make_geocoder(payload=ACTUAL, status=200, headers=None):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=payload, headers=headers)
    return Geocoder(httpx.Client(transport=httpx.MockTransport(handler))), requests


def test_real_response_streets_names_and_coordinate_order():
    geocoder, requests = make_geocoder()
    results = geocoder.search("naranjos mexicali", "es", 32.6278, -115.4545, suggest=True)
    assert len(results) == 2
    assert results[0]["name"] == "Avenida de los Naranjos, Fraccionamiento Los Pinos, Mexicali, Baja California, México"
    assert results[1]["lat"] == 32.6537055
    assert results[1]["lon"] == -115.4819467
    assert results[1]["kind"] == "street"
    params = requests[0].url.params
    assert params["lang"] == "default"  # Live demo rejects lang=es.
    assert params["lat"] == "32.6278"
    assert params["lon"] == "-115.4545"
    assert "countrycode" not in params  # Bias is not a mandatory country filter.


def test_cache_deep_copy_and_shared_suggest_submit_key():
    geocoder, requests = make_geocoder()
    result = geocoder.search("  naranjos   mexicali ", suggest=True)
    result[0]["name"] = "changed"
    second = geocoder.search("NARANJOS MEXICALI", suggest=False)
    assert second[0]["name"].startswith("Avenida")
    assert len(requests) == 1


def test_empty_is_cached_but_failures_are_not(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.geocoding.time.monotonic", lambda: now[0])
    geocoder, requests = make_geocoder({"features": []})
    assert geocoder.search("unused") == []
    assert geocoder.search("unused") == []
    assert len(requests) == 1
    geocoder, requests = make_geocoder(status=503)
    for _ in range(2):
        with pytest.raises(SearchError, match="search_unavailable"):
            geocoder.search("unused")
        now[0] += 2
    assert len(requests) == 2


def test_throttle_and_independent_lock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.geocoding.time.monotonic", lambda: now[0])
    geocoder, requests = make_geocoder()
    geocoder.search("first")
    with pytest.raises(SearchError, match="search_rate_limit"):
        geocoder.search("second")
    now[0] += 1.01
    geocoder.search("second")
    geocoder._lock.acquire()
    try:
        with pytest.raises(SearchError, match="search_rate_limit"):
            geocoder.search("third")
    finally:
        geocoder._lock.release()
    assert len(requests) == 2


def test_cache_ttl_and_size(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.geocoding.time.monotonic", lambda: now[0])
    geocoder, requests = make_geocoder()
    geocoder.cache_size = 2
    geocoder.cache_ttl = 5
    for q in ("first", "second", "third"):
        geocoder.search(q)
        now[0] += 2
    assert len(geocoder._cache) == 2
    assert not any(k[0] == "first" for k in geocoder._cache)
    now[0] += 6
    geocoder.search("third")
    assert len(requests) == 4


@pytest.mark.parametrize("payload", [{}, [], {"features": None}, {"features": [None]}])
def test_malformed_payload_is_failure_not_no_matches(payload):
    geocoder, _ = make_geocoder(payload)
    with pytest.raises(SearchError, match="search_unavailable"):
        geocoder.search("unused")


@pytest.mark.parametrize("coords", [[0, 91], [181, 0], [0, float("nan")], [True, 32], [0], ["-115", 32]])
def test_invalid_provider_coordinates_cannot_select_a_location(coords):
    payload = copy.deepcopy(ACTUAL)
    payload["features"][0]["geometry"]["coordinates"] = coords
    payload["features"] = payload["features"][:1]
    geocoder, _ = make_geocoder(payload)
    with pytest.raises(SearchError, match="search_unavailable"):
        geocoder.search("unused")


@pytest.mark.parametrize("kwargs", [
    {"q": "a"}, {"q": "x" * 201}, {"q": "valid", "lat": 32},
    {"q": "valid", "lat": float("nan"), "lon": -115},
    {"q": "valid", "lat": 91, "lon": -115}, {"q": "valid", "language": "xx"}])
def test_invalid_input_never_reaches_provider(kwargs):
    geocoder, requests = make_geocoder()
    with pytest.raises(ValueError):
        geocoder.search(**kwargs)
    assert not requests


def test_provider_429_respects_retry_after(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.geocoding.time.monotonic", lambda: now[0])
    geocoder, requests = make_geocoder(status=429, headers={"Retry-After": "10"})
    with pytest.raises(SearchError) as error:
        geocoder.search("unused")
    assert error.value.code == "search_rate_limit"
    now[0] += 2
    with pytest.raises(SearchError, match="search_rate_limit"):
        geocoder.search("another")
    assert len(requests) == 1


def test_transport_error_is_stable_and_has_no_address_in_message():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)
    geocoder = Geocoder(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(SearchError) as error:
        geocoder.search("unused")
    assert str(error.value) == "search_unavailable"


def test_endpoint_can_be_self_hosted(monkeypatch):
    monkeypatch.setenv("TLALOC_ADDRESS_GEOCODER", "http://localhost:2322/api/")
    geocoder, requests = make_geocoder()
    geocoder.search("unused")
    assert str(requests[0].url).startswith("http://localhost:2322/api/")
