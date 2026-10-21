import threading

import pytest
from app.monitoring import MonitorService
from app.origin import require_local_origin
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_saved_locations_poll_without_page_or_push_and_survive_restart(tmp_path):
    calls = []

    def analyze(location):
        calls.append(location)
        return {"coverage": {"status": "available"}, "observation_time": "2026-10-21T12:00:00Z"}

    service = MonitorService(tmp_path, analyze)
    app = FastAPI()
    app.include_router(service.router)
    body = {"name": "Mexicali", "location": {"lat": 32.6, "lon": -115.4}}
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/monitors", json=body).status_code == 403
        response = client.post("/api/monitors", json=body, headers={"Origin": "http://localhost"})
        assert response.status_code == 200
        identity = response.json()["id"]
    # No client/page and no notification subscription exists here.
    restored = MonitorService(tmp_path, analyze)
    checked = threading.Event()
    original = restored.analyze

    def background(location):
        result = original(location)
        checked.set()
        return result

    restored.analyze = background
    restored.start()
    assert checked.wait(5)
    restored.stop()
    assert len(calls) == 1
    assert restored.list()[0]["last_checked"]
    assert restored.list()[0]["last_error"] is None
    app = FastAPI()
    app.include_router(restored.router)
    with TestClient(app, base_url="http://localhost") as client:
        body["enabled"] = False
        client.post("/api/monitors", json=body, headers={"Origin": "http://localhost"})
        restored.stop_event.clear()
        restored.poll_once()
        assert len(calls) == 1
        client.delete(f"/api/monitors/{identity}", headers={"Origin": "http://localhost"})
        assert client.get("/api/monitors").json() == []


def test_monitors_limit_and_failed_observations_are_visible(tmp_path):
    service = MonitorService(tmp_path, lambda _: {"coverage": {"status": "stale_observations"}})
    app = FastAPI()
    app.include_router(service.router)
    with TestClient(app, base_url="http://localhost") as client:
        for lat in range(8):
            assert client.post("/api/monitors", json={"name": "saved", "location": {"lat": lat, "lon": 0}},
                               headers={"Origin": "http://localhost"}).status_code == 200
        assert client.post("/api/monitors", json={"name": "ninth", "location": {"lat": 9, "lon": 0}},
                           headers={"Origin": "http://localhost"}).status_code == 409
    service.poll_once()
    assert all(record["last_error"] == "stale_observations" for record in service.list())


def test_private_network_server_can_save_toggle_and_remove(tmp_path):
    service = MonitorService(tmp_path, lambda _: {})
    app = FastAPI()
    app.include_router(service.router)
    origin = "http://192.168.100.12:8001"
    body = {"name": "Casa", "location": {"lat": 32.6, "lon": -115.4}}
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        response = client.post("/api/monitors", json=body)
        assert response.status_code == 200
        identity = response.json()["id"]
        body["enabled"] = False
        assert client.post("/api/monitors", json=body).json()["enabled"] is False
        assert client.delete(f"/api/monitors/{identity}").status_code == 200


@pytest.mark.parametrize("origin", [None, "null", "http://evil.example", "http://192.168.100.12:8000",
                                    "http://192.168.100.13:8001"])
def test_lan_mutations_reject_missing_or_other_origins(tmp_path, origin):
    service = MonitorService(tmp_path, lambda _: {})
    app = FastAPI()
    app.include_router(service.router)
    headers = {"Origin": origin} if origin else {}
    with TestClient(app, base_url="http://192.168.100.12:8001") as client:
        assert client.post("/api/monitors", headers=headers,
                           json={"name": "Casa", "location": {"lat": 0, "lon": 0}}).status_code == 403


@pytest.mark.parametrize("base", ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000",
                                 "http://10.0.0.2:8001", "http://172.16.0.2:8001", "http://[fd00::2]:8001"])
def test_local_origins_remain_supported(base):
    app = FastAPI()
    from fastapi import Request

    @app.post("/")
    def mutate(request: Request):
        require_local_origin(request)
        return {"ok": True}

    with TestClient(app, base_url=base) as client:
        assert client.post("/", headers={"Origin": base}).status_code == 200
