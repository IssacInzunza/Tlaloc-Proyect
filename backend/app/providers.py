"""Public MRMS provider. URLs are assembled only from fixed hosts and verified catalog keys."""
import gzip
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import httpx

from .models import Location
from .radar import Frame, decode

S3 = "https://noaa-mrms-pds.s3.amazonaws.com"
NCEP = "https://mrms.ncep.noaa.gov/2D"
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
STAMP = re.compile(r"(\d{8}-\d{6})\.grib2\.gz$")


class ProviderError(Exception):
    pass


class RadarProvider(Protocol):
    def frames(self, location: Location, start: datetime | None = None,
               end: datetime | None = None) -> list[Frame]: ...


def regions(location: Location) -> list[str]:
    # Product domains are not national borders. Actual valid cells decide coverage.
    lat, lon = location.lat, location.lon
    result = []
    if 18 <= lat <= 57 and -133 <= lon <= -59:
        result.append("CONUS")
    if lat >= 48 and (lon <= -125 or lon >= 165):
        result.append("ALASKA")
    if 15 <= lat <= 26 and -164 <= lon <= -150:
        result.append("HAWAII")
    if 12 <= lat <= 24 and -72 <= lon <= -60:
        result.append("CARIB")
    if 10 <= lat <= 22 and 140 <= lon <= 150:
        result.append("GUAM")
    return result


class MRMSProvider:
    def __init__(self, cache: Path):
        self.cache = cache / "grib"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=True,
                                   headers={"User-Agent": "TlalocProject/1.0 personal research"})
        self.lock = threading.RLock()
        self.catalog_cache: dict = {}

    def get(self, url, limit=8_000_000):
        try:
            with self.client.stream("GET", url) as response:
                response.raise_for_status()
                chunks, length = [], 0
                for chunk in response.iter_bytes():
                    length += len(chunk)
                    if length > limit:
                        raise ProviderError("Download exceeds size limit")
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.HTTPError as error:
            raise ProviderError(type(error).__name__) from error

    def catalog(self, region: str, product: str, start: datetime, end: datetime):
        entries = []
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= end:
            prefix = f"{region}/{product}_00.00/{day:%Y%m%d}/"
            if product in ("ReflectivityAtLowestAltitude", "MergedReflectivityQCComposite"):
                prefix = f"{region}/{product}_00.50/{day:%Y%m%d}/"
            cache_key = prefix
            cached = self.catalog_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < 60:
                keys = cached[1]
            else:
                keys, continuation = [], None
                # A two-minute product has about 720 daily objects. Bound listing to two pages.
                for _ in range(2):
                    params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
                    if continuation:
                        params["continuation-token"] = continuation
                    url = str(httpx.URL(S3, params=params))
                    try:
                        root = ET.fromstring(self.get(url))
                    except ET.ParseError as error:
                        raise ProviderError("Invalid catalog XML") from error
                    keys.extend(node.text for node in root.findall("s:Contents/s:Key", NS))
                    continuation = root.findtext("s:NextContinuationToken", namespaces=NS)
                    if not continuation:
                        break
                self.catalog_cache[cache_key] = (time.monotonic(), keys)
            for key in keys:
                match = STAMP.search(key)
                if match:
                    stamp = datetime.strptime(match[1], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
                    if start <= stamp <= end:
                        entries.append((stamp, f"{S3}/{key}"))
            day += timedelta(days=1)
        return sorted(set(entries))

    def download(self, url: str) -> Path:
        import hashlib
        name = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / f"{name}.grib2"
        if path.exists() and ".latest." in url and time.time()-path.stat().st_mtime >= 60:
            path.unlink()
        if path.exists():
            # A read must not extend the freshness of a mutable latest URL.
            if ".latest." not in url:
                path.touch()
            return path
        payload = self.get(url, 16_000_000)
        try:
            # Bound inflation too; this is packed GRIB, not the decoded national raster.
            with gzip.GzipFile(fileobj=__import__("io").BytesIO(payload)) as stream:
                data = stream.read(64_000_001)
            if len(data) > 64_000_000 or not data.startswith(b"GRIB") or not data.endswith(b"7777"):
                raise ValueError("Invalid GRIB payload")
        except (OSError, EOFError, ValueError) as error:
            raise ProviderError("Invalid compressed observation") from error
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        self.cleanup()
        return path

    def cleanup(self):
        files = sorted(self.cache.glob("*.grib2"), key=lambda p: p.stat().st_mtime, reverse=True)
        total = 0
        for index, path in enumerate(files):
            total += path.stat().st_size
            if index >= 80 or total > 300_000_000 or time.time() - path.stat().st_mtime > 86400:
                path.unlink(missing_ok=True)

    def frames(self, location, start=None, end=None):
        with self.lock:
            live = start is None
            end = (end or datetime.now(UTC)).astimezone(UTC)
            start = (start or end - timedelta(minutes=22)).astimezone(UTC)
            best_frames = []
            best_coverage = -1
            for region in regions(location):
                try:
                    entries = self.catalog(region, "PrecipRate", start, end)
                except ProviderError:
                    if region != "CONUS" or not live:
                        raise
                    entries = []
                if not entries and region == "CONUS" and live:
                    # NCEP has a short rolling catalog, useful during S3 latency/outages.
                    directory = f"{NCEP}/PrecipRate/"
                    listing = self.get(directory).decode()
                    for name in set(re.findall(r'href="(MRMS_PrecipRate_[^"/]+\.grib2\.gz)"', listing)):
                        match = STAMP.search(name)
                        if match:
                            stamp = datetime.strptime(match[1], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
                            if start <= stamp <= end:
                                entries.append((stamp, directory + name))
                    entries.sort()
                if not entries:
                    if region == "CONUS" and live:
                        url = f"{NCEP}/PrecipRate/MRMS_PrecipRate.latest.grib2.gz"
                        return [decode(self.download(url), location, url)]
                    continue
                entries = entries[-6:] if live else entries[::max(1, (len(entries)+17)//18)]
                try:
                    reflectivity_entries = self.catalog(region, "ReflectivityAtLowestAltitude", start, end)
                except ProviderError:
                    reflectivity_entries = []
                try:
                    quality_entries = self.catalog(region, "RadarQualityIndex", start, end)
                except ProviderError:
                    quality_entries = []
                try:
                    composite_entries = self.catalog(region, "MergedReflectivityQCComposite", start, end)
                except ProviderError:
                    composite_entries = []
                frames = []
                for stamp, url in entries:
                    reflectivity_path = None
                    preceding_reflectivity = [entry for entry in reflectivity_entries if entry[0] <= stamp]
                    if preceding_reflectivity:
                        refl_stamp, refl_url = max(preceding_reflectivity)
                        if abs((refl_stamp-stamp).total_seconds()) <= 90:
                            try:
                                reflectivity_path = self.download(refl_url)
                            except ProviderError:
                                pass
                    quality_path = None
                    preceding_quality = [entry for entry in quality_entries if entry[0] <= stamp]
                    if preceding_quality:
                        quality_stamp, quality_url = max(preceding_quality)
                        if abs((quality_stamp-stamp).total_seconds()) <= 90:
                            try:
                                quality_path = self.download(quality_url)
                            except ProviderError:
                                pass
                    composite_path = None
                    display_entries = composite_entries if live else [entry for entry in composite_entries if entry[0] <= stamp]
                    if display_entries:
                        composite_stamp, composite_url = min(display_entries, key=lambda item: abs((item[0]-stamp).total_seconds()))
                        if abs((composite_stamp-stamp).total_seconds()) <= 90:
                            try:
                                composite_path = self.download(composite_url)
                            except ProviderError:
                                pass
                    frame = decode(self.download(url), location, url, reflectivity_path, quality_path, composite_path)
                    if abs((frame.time - stamp).total_seconds()) > 1:
                        raise ProviderError("Catalog/GRIB timestamp mismatch")
                    frame.reflectivity_source = refl_url if reflectivity_path and frame.reflectivity is not None else None
                    frame.quality_source = quality_url if quality_path and frame.quality is not None else None
                    frame.composite_reflectivity_source = composite_url if composite_path and frame.composite_reflectivity is not None else None
                    frames.append(frame)
                from .radar import coverage
                state = coverage(frames[-1], location, frames[-1].time)
                if state.target_valid and state.valid_fraction >= 0.6:
                    return frames
                if state.valid_fraction > best_coverage:
                    best_frames, best_coverage = frames, state.valid_fraction
            return best_frames
