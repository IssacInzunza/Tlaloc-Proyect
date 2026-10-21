"""Saved locations are monitored independently of Web Push subscriptions."""
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .models import Location
from .origin import require_local_origin


class SavedLocation(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    location: Location
    enabled: bool = True


class MonitorService:
    def __init__(self, directory: Path, analyze, interval=120):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "locations.json"
        self.analyze = analyze
        self.interval = max(120, interval)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.records = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.router = APIRouter(prefix="/api/monitors")
        self.router.add_api_route("", self.list, methods=["GET"])
        self.router.add_api_route("", self.save, methods=["POST"])
        self.router.add_api_route("/{identity}", self.delete, methods=["DELETE"])

    def _persist(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.records), encoding="utf-8")
        temporary.replace(self.path)

    def list(self):
        with self.lock:
            return [{"id": key, **value} for key, value in self.records.items()]

    def save(self, body: SavedLocation, request: Request):
        import hashlib
        require_local_origin(request, "monitor_same_origin_required")
        identity = hashlib.sha256(json.dumps(body.location.model_dump(), sort_keys=True).encode()).hexdigest()[:24]
        with self.lock:
            if identity not in self.records and len(self.records) >= 8:
                raise HTTPException(409, "monitor_limit")
            prior = self.records.get(identity, {})
            self.records[identity] = {**prior, **body.model_dump()}
            self._persist()
            return {"id": identity, **self.records[identity]}

    def delete(self, identity: str, request: Request):
        require_local_origin(request, "monitor_same_origin_required")
        with self.lock:
            self.records.pop(identity, None)
            self._persist()
        return {"enabled": False}

    def poll_once(self):
        for record in self.list():
            if self.stop_event.is_set():
                break
            if not record["enabled"]:
                continue
            error = None
            try:
                result = self.analyze(Location.model_validate(record["location"]))
                if result["coverage"]["status"] in ("provider_unavailable", "insufficient_coverage",
                                                      "stale_observations"):
                    error = result["coverage"]["status"]
            except Exception:
                logging.getLogger(__name__).exception("Background location analysis failed")
                result, error = {}, "analysis_failed"
            with self.lock:
                current = self.records.get(record["id"])
                if current and current["enabled"]:
                    current.update(last_checked=datetime.now(UTC).isoformat(), last_error=error,
                                   observation_time=result.get("observation_time"))
                    self._persist()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()

        def run():
            while not self.stop_event.is_set():
                try:
                    self.poll_once()
                except Exception:
                    logging.getLogger(__name__).exception("Location monitor failed")
                self.stop_event.wait(self.interval)
        self.thread = threading.Thread(target=run, daemon=True, name="tlaloc-monitors")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=20)
