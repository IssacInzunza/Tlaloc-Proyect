"""Offline integration with genuinely observed, attributed NOAA fields."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from app import main
from app.models import Location
from app.radar import coverage
from fastapi.testclient import TestClient


def test_bundled_observed_sample_integrity_and_geometry():
    root = Path(__file__).resolve().parents[2]
    metadata = json.loads((root/"samples/episode.json").read_text(encoding="utf-8"))
    assert metadata["synthetic"] is False
    assert hashlib.sha256((root/"samples/episode.npz").read_bytes()).hexdigest() == metadata["sha256"]
    location = Location(**metadata["location"])
    frames = main.sample_frames(location)
    assert len(frames) == 11
    assert all(frame.source.startswith("https://noaa-mrms-pds.s3.amazonaws.com/") for frame in frames)
    assert all(frame.reflectivity is not None and frame.quality is not None for frame in frames)
    assert coverage(frames[-1], location, frames[-1].time).quality == "radar_quality_good"


def test_actual_sample_replay_through_http_without_network(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    metadata = json.loads((root/"samples/episode.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(main, "CACHE", tmp_path)

    def never_download(*_args, **_kwargs):
        raise AssertionError("Bundled replay must not fetch replacement observations")

    monkeypatch.setattr(main.provider, "frames", never_download)
    client = TestClient(main.app)
    result = client.post("/api/replay", json={**metadata["location"], "sample": True,
        "start": metadata["frames"][0]["time"], "end": metadata["frames"][-1]["time"]})
    assert result.status_code == 200
    body = result.json()
    assert body["frame_count"] == 11
    assert body["metrics"]["target_data_availability"] == 1
    assert body["metrics"]["arrival_mae_minutes"] is None
    assert all(step["time"] == step["frame"]["time"] for step in body["steps"])
    assert all(datetime.fromisoformat(layer["time"]) <= datetime.fromisoformat(step["time"])
               for step in body["steps"] for layer in step["frame"]["layers"].values())
    assert len(client.get("/api/runs").json()) == 1
