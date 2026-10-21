import gzip
import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.models import Location
from app.providers import MRMSProvider, ProviderError, regions
from app.radar import decode


def test_domains_do_not_filter_by_national_borders():
    assert "CONUS" in regions(Location(lat=32.65, lon=-115.45))
    assert "CONUS" in regions(Location(lat=49, lon=-100))
    assert "ALASKA" in regions(Location(lat=65, lon=-147))
    assert "HAWAII" in regions(Location(lat=20, lon=-156))
    assert "GUAM" in regions(Location(lat=13.4, lon=144.8))
    assert regions(Location(lat=0, lon=0)) == []


def test_reject_invalid_compressed_payload(tmp_path, monkeypatch):
    provider = MRMSProvider(tmp_path)
    monkeypatch.setattr(provider, "get", lambda *_args: gzip.compress(b"not a GRIB"))
    with pytest.raises(ProviderError):
        provider.download("https://noaa-mrms-pds.s3.amazonaws.com/test.grib2.gz")
    assert not list(provider.cache.glob("*.grib2"))


def test_download_size_is_bounded(tmp_path):
    provider = MRMSProvider(tmp_path)
    provider.client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"12345")))
    with pytest.raises(ProviderError, match="size limit"):
        provider.get("https://example.invalid", limit=4)


def test_latest_alias_is_refreshed(tmp_path, monkeypatch):
    provider = MRMSProvider(tmp_path)
    calls = []
    monkeypatch.setattr(provider, "get", lambda *_args: calls.append(1) or gzip.compress(b"GRIBtest7777"))
    path = provider.download("https://example.invalid/MRMS.latest.grib2.gz")
    provider.download("https://example.invalid/MRMS.latest.grib2.gz")
    assert len(calls) == 1
    os.utime(path, (0, 0))
    provider.download("https://example.invalid/MRMS.latest.grib2.gz")
    assert len(calls) == 2


def test_reading_latest_alias_does_not_extend_its_freshness(tmp_path, monkeypatch):
    provider = MRMSProvider(tmp_path)
    calls = []
    monkeypatch.setattr(provider, "get", lambda *_args: calls.append(1) or gzip.compress(b"GRIBtest7777"))
    url = "https://example.invalid/MRMS.latest.grib2.gz"
    path = provider.download(url)
    downloaded = path.stat().st_mtime
    monkeypatch.setattr("app.providers.time.time", lambda: downloaded + 40)
    provider.download(url)
    assert path.stat().st_mtime == downloaded
    monkeypatch.setattr("app.providers.time.time", lambda: downloaded + 61)
    provider.download(url)
    assert len(calls) == 2


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("TLALOC_NETWORK_TESTS") != "1", reason="Opt-in real NOAA download")
def test_real_noaa_grib(tmp_path):
    provider = MRMSProvider(tmp_path)
    location = Location(lat=32.65, lon=-115.45)
    end = datetime.now(UTC)
    entries = provider.catalog("CONUS", "PrecipRate", end-timedelta(minutes=20), end)
    assert entries
    stamp, url = entries[-1]
    frame = decode(provider.download(url), location, url)
    assert frame.time == stamp
    assert frame.rate.shape[0] <= 241
    assert frame.source.startswith("https://noaa-mrms-pds.s3.amazonaws.com/")
