"""Address/search-as-you-type adapter. Call only after external-search consent.

Photon uses OpenStreetMap addresses, so incomplete mapping can still yield no
matches. Queries and coordinates are cached briefly in RAM, never on disk.
https://github.com/komoot/photon/blob/master/docs/api-v1.md
"""
import copy
import math
import os
import threading
import time
from collections import OrderedDict

import httpx


class SearchError(RuntimeError):
    def __init__(self, code="search_unavailable"):
        self.code = code
        super().__init__(code)


class Geocoder:
    def __init__(self, client=None, *, endpoint=None, cache_ttl=300, cache_size=128):
        self.endpoint = endpoint or os.environ.get(
            "TLALOC_ADDRESS_GEOCODER", "https://photon.komoot.io/api/")
        self.client = client or httpx.Client(
            timeout=8, headers={"User-Agent": "TlalocProject/1.0 (local weather application)"})
        self.cache_ttl = cache_ttl
        self.cache_size = max(1, cache_size)
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._last_request = -math.inf
        self._blocked_until = -math.inf

    def close(self):
        self.client.close()

    def search(self, q, language="en", lat=None, lon=None, suggest=False):
        q = " ".join(q.split())
        if not 2 <= len(q) <= 200:
            raise ValueError("invalid_search_query")
        if language not in ("en", "es"):
            raise ValueError("invalid_search_language")
        if (lat is None) != (lon is None):
            raise ValueError("invalid_search_location")
        if lat is not None and (not math.isfinite(lat) or not math.isfinite(lon)
                                or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            raise ValueError("invalid_search_location")
        # Both modes use Photon, whose public API explicitly allows autocomplete.
        # Never route suggestions to the public Nominatim service.
        key = (q.casefold(), language, lat, lon)
        if not self._lock.acquire(blocking=False):
            raise SearchError("search_rate_limit")
        try:
            now = time.monotonic()
            for expired in [k for k, (saved, _) in self._cache.items()
                            if now - saved >= self.cache_ttl]:
                del self._cache[expired]
            cached = self._cache.get(key)
            if cached:
                self._cache.move_to_end(key)
                return copy.deepcopy(cached[1])
            if now < self._blocked_until or now - self._last_request < 1:
                raise SearchError("search_rate_limit")
            # The demo supports en/de/fr/default, not es. Local OSM names keep
            # Spanish streets readable rather than causing an upstream HTTP 400.
            params = {"q": q, "lang": "en" if language == "en" else "default", "limit": 6}
            if lat is not None:
                params.update(lat=lat, lon=lon, zoom=12, location_bias_scale=0.2)
            self._last_request = now
            try:
                response = self.client.get(self.endpoint, params=params)
                if response.status_code == 429:
                    try:
                        retry = float(response.headers.get("Retry-After", 5))
                    except ValueError:
                        retry = 5
                    self._blocked_until = time.monotonic() + min(300, max(1, retry))
                    raise SearchError("search_rate_limit")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
                    raise SearchError()
                results = self._parse(payload["features"])
                if payload["features"] and not results:
                    raise SearchError()
            except (httpx.HTTPError, ValueError, TypeError) as error:
                raise SearchError() from error
            self._cache[key] = (time.monotonic(), results)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return copy.deepcopy(results)
        finally:
            self._lock.release()

    @staticmethod
    def _parse(features):
        results, seen = [], set()
        for feature in features:
            if not isinstance(feature, dict):
                continue
            props, geom = feature.get("properties"), feature.get("geometry")
            if not isinstance(props, dict) or not isinstance(geom, dict) or geom.get("type") != "Point":
                continue
            coords = geom.get("coordinates")
            if not isinstance(coords, list) or len(coords) != 2:
                continue
            lon, lat = coords
            if (isinstance(lat, bool) or isinstance(lon, bool)
                    or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
                    or not math.isfinite(lat) or not math.isfinite(lon)
                    or not -90 <= lat <= 90 or not -180 <= lon <= 180):
                continue
            text = lambda field, data=props: str(data.get(field) or "").strip()
            street = " ".join(filter(None, [text("street"), text("housenumber")]))
            primary = text("name") or street
            if not primary:
                continue
            pieces = [primary]
            if street and street != primary:
                pieces.append(street)
            for field in ("locality", "district", "city", "state", "country"):
                value = text(field)
                if value and value.casefold() not in [part.casefold() for part in pieces]:
                    pieces.append(value)
            name = ", ".join(pieces)
            identity = (name.casefold(), round(lat, 5), round(lon, 5))
            if identity in seen:
                continue
            seen.add(identity)
            results.append({"name": name, "lat": lat, "lon": lon,
                            "kind": text("type") or text("osm_value") or "place",
                            "provider": "Photon / OpenStreetMap"})
            if len(results) == 6:
                break
        return results
