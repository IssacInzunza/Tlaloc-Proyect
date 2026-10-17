import base64
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.notifications import NotificationService, Subscription

NOW = 1792260000.0


def encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def body():
    public = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"location": {"lat": 32.6, "lon": -115.4}, "language": "es",
            "levels": ["preventive", "imminent"], "subscription": {
                "endpoint": "https://fcm.googleapis.com/fcm/send/fake-local-test",
                "keys": {"p256dh": encode(public), "auth": encode(bytes(16))}}}


def analysis(rate=0, level="preventive", age=60, quality="radar_quality_good"):
    stamp = datetime.fromtimestamp(NOW-age, UTC).isoformat()
    return {"observation_time": stamp, "target_rate": rate,
            "coverage": {"target_valid": True, "valid_fraction": 1, "status": "available", "quality": quality},
            "predictions": [{"id": "a", "level": level, "confidence": "high", "data_quality": quality,
                             "arrival_minutes": [5, 12], "observation_time": stamp}]}


@pytest.fixture
def setup(tmp_path):
    delivered = []
    current = [analysis()]
    service = NotificationService(tmp_path, lambda location: current[0], clock=lambda: NOW,
                                  transport=lambda subscription, payload: delivered.append(payload))
    app = FastAPI()
    app.include_router(service.router)
    client = TestClient(app, base_url="http://127.0.0.1:8000", headers={"Origin": "http://127.0.0.1:8000"})
    response = client.post("/api/notifications/subscribe", json=body())
    assert response.status_code == 200
    return service, client, response.json()["id"], delivered, current


def test_only_opted_in_subscription_sends_and_cooldown_survives_restart(setup, tmp_path):
    service, client, token, delivered, current = setup
    service.poll_once()
    current[0]["predictions"][0]["id"] = "new-id"
    service.poll_once()
    assert len(delivered) == 1
    resumed = NotificationService(tmp_path, lambda location: current[0], clock=lambda: NOW,
                                   transport=lambda subscription, payload: delivered.append(payload))
    assert resumed.public_key == service.public_key
    resumed.poll_once()
    assert len(delivered) == 1
    assert client.get(f"/api/notifications/{token}/status").json()["last_sent"]
    assert "32.6" not in str(delivered) and "-115.4" not in str(delivered)


@pytest.mark.parametrize("change", [
    {"age": 601}, {"age": -1}, {"quality": "product_mask_only"},
    {"quality": "radar_quality_limited"}, {"rate": float("nan")}, {"rate": None}, {"level": "informational"},
])
def test_unsuitable_observations_never_send(setup, change):
    service, _, _, delivered, current = setup
    current[0] = analysis(**change)
    service.poll_once()
    assert delivered == []


def test_wet_onset_only_rearms_on_observed_valid_dry(setup):
    service, _, _, delivered, current = setup
    current[0] = analysis(rate=2)
    service.poll_once()
    current[0] = analysis(rate=None)
    service.poll_once()
    current[0] = analysis(rate=2)
    service.poll_once()
    assert len(delivered) == 1
    current[0] = analysis(rate=0, level="informational")
    service.poll_once()
    current[0] = analysis(rate=2)
    service.poll_once()
    assert len(delivered) == 2


def test_permission_same_origin_and_capability(setup):
    _, client, token, _, _ = setup
    response = client.post("/api/notifications/subscribe", json=body(), headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.delete(f"/api/notifications/{token}", headers={"Origin": "null"}).status_code == 403
    assert client.get("/api/notifications/unknown/status").status_code == 404
    assert client.delete(f"/api/notifications/{token}").json() == {"enabled": False}
    assert client.get(f"/api/notifications/{token}/status").status_code == 404


@pytest.mark.parametrize("endpoint", ["http://fcm.googleapis.com/test", "https://127.0.0.1/test",
    "https://fcm.googleapis.com.evil.example/test", "https://user@fcm.googleapis.com/test",
    "https://fcm.googleapis.com:8443/test", "https://evil.example/test", "https://notify.windows.com/test"])
def test_arbitrary_endpoints_rejected(endpoint):
    value = body()["subscription"]
    value["endpoint"] = endpoint
    with pytest.raises(ValidationError):
        Subscription.model_validate(value)


def test_expired_push_endpoint_disables_local_watch(setup):
    service, client, token, _, _ = setup
    class Expired(Exception):
        status_code = 410
    def fail(*args):
        raise Expired("secret-endpoint-should-never-be-returned")
    service.transport = fail
    service.poll_once()
    result = client.get(f"/api/notifications/{token}/status").json()
    assert result["enabled"] is False
    assert result["last_error"] == "notification_subscription_expired"


def test_rate_limit_backoff_and_test_is_labeled(setup):
    service, client, token, delivered, _ = setup
    assert client.post(f"/api/notifications/{token}/test").json() == {"sent": True}
    assert delivered[0]["title"] == "Prueba de Tláloc"
    assert client.post(f"/api/notifications/{token}/test").status_code == 429
    class Limited(Exception):
        status_code = 429
    attempts = []
    def fail(*args):
        attempts.append(1)
        raise Limited()
    service.transport = fail
    service.poll_once()
    service.poll_once()
    assert len(attempts) == 1
    assert client.get(f"/api/notifications/{token}/status").json()["last_error"] == "notification_push_rate_limited"


def test_bad_prediction_timestamp_is_not_used(setup):
    service, _, _, delivered, current = setup
    current[0]["predictions"][0]["observation_time"] = "2020-01-01T00:00:00+00:00"
    service.poll_once()
    assert not delivered


@pytest.mark.parametrize("levels", [["informational", "preventive", "imminent"], []])
def test_frontend_levels_contract(setup, levels):
    _, client, _, _, _ = setup
    value = body()
    value["levels"] = levels
    assert client.post("/api/notifications/subscribe", json=value).status_code == 200


@pytest.mark.parametrize("interval", [[-1, 10], [10, 5], [0, 61], [0, float("inf")], [], ["0", 5]])
def test_bad_forecast_arrival_is_never_sent(setup, interval):
    service, _, _, delivered, current = setup
    current[0]["predictions"][0]["arrival_minutes"] = interval
    service.poll_once()
    assert not delivered


def test_changed_watch_drops_previous_location_cooldown_and_timestamp(setup):
    service, client, token, delivered, current = setup
    service.poll_once()
    assert len(delivered) == 1
    value = body()
    value.pop("subscription")
    value["location"]["lat"] = 33
    response = client.post(f"/api/notifications/{token}/update", json=value)
    assert response.status_code == 200
    # NOAA can provide an older (still valid) latest frame for the new tile.
    current[0] = analysis(age=120)
    service.poll_once()
    assert len(delivered) == 2
