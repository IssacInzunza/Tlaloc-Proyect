"""Opt-in Web Push watches, persisted on this computer only.

The worker never derives rain from display-only reflectivity. Transport and clock
are injectable so tests cannot accidentally send a real notification.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Location
from .origin import require_local_origin


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("invalid_push_key")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p256dh: str = Field(max_length=100)
    auth: str = Field(max_length=30)

    @field_validator("p256dh")
    @classmethod
    def curve_point(cls, value):
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _decode(value))
        return value

    @field_validator("auth")
    @classmethod
    def auth_key(cls, value):
        if len(_decode(value)) != 16:
            raise ValueError("invalid_push_auth")
        return value


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(max_length=2048)
    keys: PushKeys
    expirationTime: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("endpoint")
    @classmethod
    def public_push_endpoint(cls, value):
        endpoint = urlsplit(value)
        host = endpoint.hostname or ""
        allowed = host in {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"}
        allowed |= host.endswith(".notify.windows.com") and host != "notify.windows.com"
        allowed |= host.endswith(".push.apple.com")
        if (not allowed or endpoint.scheme != "https" or endpoint.port not in (None, 443)
                or endpoint.username or endpoint.password or endpoint.fragment
                or not endpoint.path or endpoint.path == "/"):
            raise ValueError("unsupported_push_endpoint")
        return value


class Watch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location: Location
    language: Literal["en", "es"] = "es"
    levels: list[Literal["informational", "preventive", "imminent"]] = Field(
        default_factory=lambda: ["preventive", "imminent"], max_length=3)


class Subscribe(Watch):
    subscription: Subscription


class NotificationError(Exception):
    def __init__(self, code: str, status: int = 503):
        self.code, self.status = code, status
        super().__init__(code)


class NotificationService:
    def __init__(self, cache: Path, analyze_callback, *, transport=None, clock=time.time, interval=120):
        self.directory = Path(cache) / "notifications"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "watches.json"
        self.key_path = self.directory / "vapid.pem"
        self.analyze = analyze_callback
        self.clock = clock
        self.transport = transport or self._webpush
        self.interval = max(120, interval)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.records = self._load()
        self.public_key = self._key()
        self.router = self._router()

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or len(data) > 8:
                raise ValueError()
            for token, record in data.items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
                    raise ValueError()
                Subscribe.model_validate(record["watch"])
            return data
        except (ValueError, KeyError, TypeError):
            # Fail visibly, never overwrite subscriptions after a corrupt read.
            raise NotificationError("notification_storage_invalid") from None

    @staticmethod
    def _private_write(path, content):
        temporary = path.with_suffix(path.suffix + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def _save(self):
        self._private_write(self.path, json.dumps(self.records, ensure_ascii=False))

    def _key(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        if self.key_path.exists():
            private = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        else:
            private = ec.generate_private_key(ec.SECP256R1())
            pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()).decode("ascii")
            self._private_write(self.key_path, pem)
        return _b64(private.public_key().public_bytes(serialization.Encoding.X962,
                                                     serialization.PublicFormat.UncompressedPoint))

    @staticmethod
    def _same_origin(request: Request):
        require_local_origin(request, "notification_same_origin_required")

    def _record(self, token):
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token) or token not in self.records:
            raise HTTPException(404, "notification_not_found")
        return self.records[token]

    def _router(self):
        router = APIRouter(prefix="/api/notifications")

        @router.get("/config")
        def config():
            return {"public_key": self.public_key, "enabled": True}

        @router.post("/subscribe")
        def subscribe(body: Subscribe, request: Request):
            self._same_origin(request)
            with self.lock:
                # Same endpoint belongs to only one capability; revoke the old one.
                existing = next((key for key, value in self.records.items()
                                 if value["watch"]["subscription"]["endpoint"] == body.subscription.endpoint), None)
                if len(self.records) >= 8 and existing is None:
                    raise HTTPException(409, "notification_subscription_limit")
                if existing:
                    del self.records[existing]
                token = secrets.token_urlsafe(32)
                self.records[token] = {"watch": body.model_dump(), "enabled": True,
                                       "last_checked": None, "last_sent": None, "last_error": None,
                                       "wet": False, "seen": [], "failures": 0, "retry_at": 0}
                self._save()
            return {"id": token, "enabled": True}

        @router.get("/{token}/status")
        def status(token: str):
            with self.lock:
                record = self._record(token)
                return {key: record.get(key) for key in ("enabled", "last_checked", "last_sent", "last_error")}

        @router.post("/{token}/update")
        def update(token: str, body: Watch, request: Request):
            self._same_origin(request)
            with self.lock:
                record = self._record(token)
                location_changed = body.location.model_dump() != record["watch"]["location"]
                record["watch"].update(body.model_dump())
                if location_changed:
                    record.update(wet=False, seen=[], level_sent={}, observation_epoch=0)
                self._save()
                return {"id": token, "enabled": record["enabled"]}

        @router.delete("/{token}")
        def delete(token: str, request: Request):
            self._same_origin(request)
            with self.lock:
                self._record(token)
                del self.records[token]
                self._save()
            return {"enabled": False}

        @router.post("/{token}/test")
        def test(token: str, request: Request):
            self._same_origin(request)
            with self.lock:
                record = self._record(token)
                if not record["enabled"]:
                    raise HTTPException(409, "notification_subscription_expired")
                if self.clock() - record.get("test_at", 0) < 30:
                    raise HTTPException(429, "notification_test_rate_limited")
                record["test_at"] = self.clock()
                error = self._deliver(record, self._payload("test", record["watch"]["language"]))
                self._save()
                if error:
                    raise HTTPException(503, error)
            return {"sent": True}
        return router

    def _webpush(self, subscription, payload):
        import requests
        from pywebpush import webpush

        class NoRedirectSession(requests.Session):
            def request(self, method, url, **kwargs):
                kwargs["allow_redirects"] = False
                return super().request(method, url, **kwargs)

        with NoRedirectSession() as session:
            response = webpush(subscription_info=subscription, data=json.dumps(payload, ensure_ascii=False),
                               vapid_private_key=str(self.key_path),
                               vapid_claims={"sub": "mailto:notifications@tlaloc.local"},
                               ttl=120, timeout=15, requests_session=session)
            if response.status_code >= 300:
                error = NotificationError("notification_delivery_failed")
                error.response = response
                raise error

    def _deliver(self, record, payload):
        if self.clock() < record.get("retry_at", 0):
            return "notification_retry_pending"
        try:
            self.transport(record["watch"]["subscription"], payload)
        except Exception as exc:  # noqa: BLE001 - redact provider exceptions containing subscription secrets.
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
            record["failures"] = min(record.get("failures", 0) + 1, 10)
            if status in (404, 410):
                record["enabled"] = False
                code = "notification_subscription_expired"
            else:
                code = "notification_push_rate_limited" if status == 429 else "notification_delivery_failed"
                delay = min(3600, 120 * 2 ** min(record["failures"], 5))
                if status == 429 and response is not None:
                    try:
                        delay = min(86400, max(delay, int(response.headers.get("Retry-After", delay))))
                    except (ValueError, TypeError):
                        pass
                record["retry_at"] = self.clock() + delay
            record["last_error"] = code
            return code
        record.update(last_sent=self._iso(), last_error=None, failures=0, retry_at=0)
        return None

    def _iso(self):
        return datetime.fromtimestamp(self.clock(), UTC).isoformat()

    @staticmethod
    def _payload(kind, language):
        spanish = language == "es"
        messages = {
            "test": ("Prueba de Tláloc", "Las notificaciones de lluvia están activadas.") if spanish else
                    ("Tláloc test", "Rain notifications are enabled."),
            "wet": ("Precipitación detectada", "El radar estima lluvia en tu ubicación vigilada.") if spanish else
                   ("Precipitation detected", "Radar estimates rain at your watched location."),
            "imminent": ("Lluvia próxima", "El radar sugiere llegada de lluvia en los próximos minutos. Revisa Tláloc.") if spanish else
                        ("Rain approaching", "Radar suggests rain arrival in the next few minutes. Check Tláloc."),
            "preventive": ("Posible llegada de lluvia", "Una región de lluvia podría llegar pronto. Pronóstico experimental; revisa Tláloc.") if spanish else
                          ("Possible rain arrival", "A rain region could arrive soon. Experimental forecast; check Tláloc."),
        }
        title, body = messages[kind]
        return {"title": title, "body": body, "tag": f"tlaloc-{kind}", "url": "/"}

    def _eligible(self, analysis):
        coverage = analysis.get("coverage") or {}
        try:
            stamp = datetime.fromisoformat(str(analysis["observation_time"]))
            age = self.clock() - stamp.timestamp() if stamp.tzinfo else math.inf
            return (0 <= age <= 600 and coverage.get("target_valid") is True
                    and coverage.get("valid_fraction", 0) >= .6
                    and coverage.get("status") in ("available", "partial_coverage", "no_precipitation_detected")
                    and coverage.get("quality") == "radar_quality_good")
        except (KeyError, ValueError, TypeError):
            return False

    def _forecast_eligible(self, prediction, watch, observation):
        try:
            stamp = datetime.fromisoformat(str(prediction["observation_time"]))
            age = self.clock() - stamp.timestamp() if stamp.tzinfo else math.inf
            interval = prediction["arrival_minutes"]
            return (prediction.get("level") in ("preventive", "imminent")
                    and prediction.get("level") in watch.levels
                    and prediction.get("confidence") in ("medium", "high")
                    and prediction.get("data_quality") == "radar_quality_good"
                    and 0 <= age <= 600 and str(prediction["observation_time"]) == str(observation)
                    and isinstance(interval, list) and len(interval) == 2
                    and all(isinstance(v, (float, int)) and math.isfinite(v) for v in interval)
                    and 0 <= interval[0] <= interval[1] <= 60)
        except (KeyError, ValueError, TypeError):
            return False

    def poll_once(self):
        # Do not hold storage lock while NOAA analysis may be downloading data.
        with self.lock:
            tokens = list(self.records)
        for token in tokens:
            if self.stop_event.is_set():
                break
            with self.lock:
                record = self.records.get(token)
                if not record or not record["enabled"] or self.clock() < record.get("retry_at", 0):
                    continue
                watch = Subscribe.model_validate(record["watch"])
            try:
                analysis = self.analyze(watch.location)
            except Exception:  # noqa: BLE001 - callback failure must not leak weather-query or provider secrets.
                with self.lock:
                    if token in self.records:
                        self.records[token].update(last_checked=self._iso(), last_error="notification_analysis_unavailable")
                        self._save()
                continue
            with self.lock:
                record = self.records.get(token)
                if not record or not record["enabled"] or record["watch"] != watch.model_dump():
                    continue
                record["last_checked"] = self._iso()
                if not self._eligible(analysis):
                    record["last_error"] = "notification_observations_unsuitable"
                    self._save()
                    continue
                observation = str(analysis["observation_time"])
                # ISO times from the analysis are aware and consistently UTC.
                stamp = datetime.fromisoformat(observation).timestamp()
                if stamp < record.get("observation_epoch", 0):
                    continue
                record["observation_epoch"] = stamp
                record["last_error"] = None
                rate = analysis.get("target_rate")
                finite_rate = isinstance(rate, (int, float)) and not isinstance(rate, bool) and math.isfinite(rate) and rate >= 0
                wet = finite_rate and rate >= watch.location.threshold
                if finite_rate and not wet:
                    record["wet"] = False
                if wet and not record["wet"]:
                    if self._deliver(record, self._payload("wet", watch.language)) is None:
                        record["wet"] = True
                elif not wet and finite_rate:
                    candidates = [prediction for prediction in analysis.get("predictions", [])
                                  if self._forecast_eligible(prediction, watch, observation)]
                    candidates.sort(key=lambda prediction: prediction.get("level") != "imminent")
                    for prediction in candidates:
                        # Region IDs survive tracking; each level is sent once per
                        # region episode, rather than again on each radar timestamp.
                        level = prediction["level"]
                        identity = f"{observation}:{prediction.get('id')}:{level}"
                        # Tracker IDs can change when an episode leaves RAM. Bound
                        # notifications per level even if cells are reassigned.
                        if (identity in record["seen"] or self.clock() -
                                record.get("level_sent", {}).get(level, 0) < 1800):
                            continue
                        if self._deliver(record, self._payload(level, watch.language)) is None:
                            record["seen"] = (record["seen"] + [identity])[-128:]
                            record.setdefault("level_sent", {})[level] = self.clock()
                        break
                self._save()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()

        def run():
            while not self.stop_event.is_set():
                try:
                    self.poll_once()
                except Exception:  # noqa: BLE001 - background worker boundary records only stable error codes.
                    # No subscription/key details go to logs; a storage/worker
                    # failure is represented in local status when possible.
                    with self.lock:
                        for record in self.records.values():
                            record["last_error"] = "notification_worker_failed"
                self.stop_event.wait(self.interval)
        self.thread = threading.Thread(target=run, name="tlaloc-notifications", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=20)
