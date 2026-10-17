"""Local SQLite alert lifecycle, scoped to the watched location and analysis settings."""
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from .models import Location, Prediction


class AlertHistory:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS events (
            scope TEXT, id TEXT, observed TEXT, action TEXT, payload TEXT,
            UNIQUE(scope,id,observed,action))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS active (
            scope TEXT, id TEXT, payload TEXT, PRIMARY KEY(scope,id))""")
        self.db.commit()

    @staticmethod
    def scope(location: Location):
        return json.dumps(location.model_dump(), sort_keys=True)

    def update(self, location: Location, predictions: list[Prediction], observation: str,
               unavailable=False):
        scope = self.scope(location)
        with self.lock, self.db:
            old = dict(self.db.execute("SELECT id,payload FROM active WHERE scope=?", (scope,)))
            new = {p.id: p.model_dump(mode="json") for p in predictions}
            for identity, payload in new.items():
                prior = json.loads(old[identity]) if identity in old else None
                significant = prior is None or any(prior[k] != payload[k] for k in ("level", "event", "intensity"))
                if significant:
                    self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
                                    (scope, identity, observation, "created" if prior is None else "updated",
                                     json.dumps(payload)))
                self.db.execute("INSERT OR REPLACE INTO active VALUES (?,?,?)",
                                (scope, identity, json.dumps(payload)))
            for identity in old.keys()-new.keys():
                self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
                                (scope, identity, observation, "suspended" if unavailable else "cancelled", old[identity]))
                self.db.execute("DELETE FROM active WHERE scope=? AND id=?", (scope, identity))
            self.db.execute("DELETE FROM events WHERE rowid NOT IN (SELECT rowid FROM events ORDER BY rowid DESC LIMIT 2000)")

    def list(self, location: Location):
        with self.lock:
            rows = self.db.execute("SELECT observed,action,payload FROM events WHERE scope=? ORDER BY rowid DESC LIMIT 100",
                                   (self.scope(location),)).fetchall()
        return [{"time": time, "action": action, "alert": json.loads(payload)} for time, action, payload in rows]

    def suspend(self, location):
        self.update(location, [], datetime.now(UTC).isoformat(), unavailable=True)
