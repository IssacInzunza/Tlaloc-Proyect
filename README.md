# Tláloc Project

[Español](docs/README.es.md) · Version 1.0.0 · MIT

Tláloc Project is an open-source experimental weather radar application for hyperlocal precipitation tracking and short-term rainfall arrival estimation using NOAA radar data.

Tláloc runs on your computer. Select a point, watch a fixed 10–100 km geographic circle (50 km initially), and inspect actual NOAA MRMS observations. The application tracks observed precipitation footprints and reports qualitative motion confidence and approximate arrival intervals when evidence supports them. It cannot predict storms that have not formed and is not an official warning system.

## What works

- Interactive Leaflet map, address/place search with debounced suggestions, coordinates, click/drag target, optional GPS, radius and segmentation threshold settings.
- English and Spanish, browser language detection, remembered language/location/alert preferences.
- Real NOAA PrecipRate GRIB2 ingestion, low-altitude reflectivity trends, composite-reflectivity display and optional Radar Quality Index (RQI); bounded caches and region-specific coverage checks.
- Radar animation, timestamps, missing-data overlay, region footprints and motion vectors.
- Connected-component tracking with a phase-correlation translation prior, conservative association, footprint extrapolation and informational/preventive/imminent attention levels.
- Local SQLite alert lifecycle and history, enabled-level filters and optional user-activated audio.
- Chronological historical replay, a small real NOAA episode bundled for offline replay, diagnostic metrics, saved run comparison and JSON export.
- FastAPI OpenAPI documentation, deterministic tests and an opt-in actual NOAA integration test.

## Requirements

Python **3.12 or newer**, Node.js **20.19+**, npm, and an ordinary CPU. No API key, account, GPU, paid weather service, or public infrastructure is required. Use 64-bit Python with binary wheels for NumPy, OpenCV, rasterio/GDAL and pyproj. Initial dependency installation needs internet access. Windows 11 was exercised here; the Linux commands below are provided but have not been executed on Linux in this session.

## Windows 11

Open PowerShell in the repository:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
npm run build
cd ..
powershell -ExecutionPolicy Bypass -File scripts\run.ps1
```

Open [Tláloc locally](http://127.0.0.1:8000). Stop with Ctrl+C. The script binds to loopback. In the current Codex workspace `.venv` and the frontend build are already installed. That bundled Python environment has no pip module; to update it, use `python -m pip --python .venv/Scripts/python.exe install -r backend/requirements.txt` from the separately installed system Python.

## Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
bash scripts/run.sh
```

If venv support is missing, install your distribution's Python venv package. If pip cannot find a binary geospatial wheel for your platform, a system GDAL/PROJ installation or a supported Python version may be needed; the app does not hide a decoder failure behind synthetic data.

## Development

Run the backend and Vite in separate terminals:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run dev
```

Open [Vite](http://127.0.0.1:5173). Vite proxies `/api` to port 8000. After frontend changes rebuild `frontend/dist` before using the single-server production UI. API schemas are at [OpenAPI](http://127.0.0.1:8000/docs).

## First use and historical replay

1. Choose a city, enter coordinates, or click/drag the map target. GPS is optional and starts only when you press My location.
2. Inspect observation age, valid-area fraction and RQI quality. The map initially displays estimated precipitation (mm/h); selecting reflectivity (dBZ) saves that preference locally for the next visit. Gray pixels mean missing values in the selected layer. The overlay covers only the watch radius plus a 20 km processing margin, not the whole visible map.
3. Play the timeline. Live predictions appear only on the latest frame. A circle indicates the search area, not an area forecast to receive rain.
4. Open Historical replay → Load real example for a bundled 11-frame NOAA episode at 27°N, 82.5°W on October 17, 2026, 08:00–08:20 UTC. This episode demonstrates actual rain, uncertain broad regions and chronology. It has no verified target arrival; null arrival metrics are expected.
5. To query the archive, select a 2–60 minute UTC period and Run analysis. Catalog availability varies by product, date and domain. At most 18 actual observations are loaded; no absent frames are fabricated.

Replay never uses later observations to build earlier forecasts. Future observations are used only in validation. Metrics compare against sampled radar estimates, not rain gauges. They do not establish operational accuracy. See [testing and metric definitions](docs/testing.md).

## Interpretation and limits

PrecipRate is a NOAA **estimated rain rate in mm/h**. Composite reflectivity in **dBZ** displays observed echoes aloft (maximum through a vertical column), not confirmed surface rain. Low-altitude reflectivity remains separate for trends. Tláloc never converts displayed dBZ into measured rain rates or uses display-only composite echoes to generate rate-based arrival alerts. No Doppler radial velocity is used as storm translation.

Arrival intervals and confidence labels are engineering heuristics, not calibrated probabilities. New echoes, ambiguous splits/merges, clipped regions and unreliable motion remain informational. Conservative checks frequently withhold an arrival estimate. High-confidence imminent alerts require good actual RQI. Motion beyond 30 minutes is treated as too uncertain for a numeric interval in this initial implementation; the footprint intersection engine evaluates up to 60 minutes.

Live data currently use MRMS domain discovery/selection rather than a per-site NEXRAD decoder. NOAA does not provide global radar coverage. Border locations are allowed; valid product pixels decide usability. Regional catalog support exists for CONUS, Alaska, Hawaii, Caribbean and Guam, but only CONUS GRIB ingestion was exercised in this session. Terrain, beam height, melting layer, non-rain echoes, evolving cells and source outages limit results. RQI helps, but cannot certify ground rainfall. Read [limitations](docs/limitations.md) before interpreting alerts. Follow official local weather authorities.

## Tests

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp=.cache/pytest-local
.venv/Scripts/python.exe -m ruff check backend scripts
cd frontend
npm test
npm run build
```

The real NOAA integration test is opt-in:

```powershell
$env:TLALOC_NETWORK_TESTS = '1'
.venv/Scripts/python.exe -m pytest backend/tests/test_provider.py -m integration -q --basetemp=.cache/pytest-network
```

On Linux use `TLALOC_NETWORK_TESTS=1 .venv/bin/python -m pytest ...`. Windows sandboxing may block asyncio's internal socket pair; the API test client then needs an environment that permits loopback sockets. This is distinct from a NOAA outage.

With the production server running at port 8000, `cd frontend` and run `npm run test:e2e` to exercise the actual browser app, language persistence, marker drag, radius controls and real bundled replay. Windows uses installed Edge. On Linux, install Playwright's Chromium with `npx playwright install chromium` first; `TLALOC_BROWSER_CHANNEL` can select another installed compatible channel. The test uses real public map tiles and writes review screenshots under `.cache/browser/`.

## Data, privacy and licenses

Radar: [NOAA MRMS](https://www.nssl.noaa.gov/projects/mrms/), via [NODD public S3](https://registry.opendata.aws/noaa-mrms-pds/) and NCEP. Data are processed/reprojected by Tláloc; no NOAA endorsement is implied. Bundled sample provenance and checksum: [episode.json](samples/episode.json).

Map tiles: OpenStreetMap contributors, with attribution on the map. Address suggestions: Photon/OpenStreetMap, enabled by default under the user’s authorization. Public-service usage terms and availability limits apply; coverage depends on mapped addresses, so a particular house number may be absent. See [data sources](docs/data-sources.md).

There is no telemetry or account system. The last **live watch location** and preferences stay in browser LocalStorage. Historical/sample positions are temporary and do not overwrite that watch; returning to Live or reloading restores it. Storage is specific to the same browser and URL origin: `localhost` and `127.0.0.1` have different local stores, and private sessions may discard data. No saved watch preference is uploaded to a remote server.

SQLite alert history, caches and metric summaries stay under this computer's `.cache/` by default; coordinates occur in that local history. The loopback API receives the point for local cropping. Map providers receive tile requests. Photon receives typed search text and the map center rounded to two decimals for ranking; queries are briefly cached in RAM, never written to query files. The run scripts disable HTTP access logging. NOAA downloads request domain products, not private-location URLs. Optional `TLALOC_CACHE` and `TLALOC_ADDRESS_GEOCODER` variables are described in `.env.example`.

Source code is [MIT](LICENSE); NOAA data and third-party services retain their own terms. See [architecture](docs/architecture.md), [processing](docs/radar-processing.md), [tracking](docs/tracking-algorithm.md), [nowcasting](docs/nowcasting.md) and [PROGRESS](PROGRESS.md).

### Background rain notifications

Open Settings in full Edge or Chrome, enable rain notifications and accept the browser permission. The local computer and Tláloc server must remain running after closing the tab. The watched point and subscription are stored only on this computer; encrypted messages pass through the browser push service without coordinates. Use Send test notification to verify your browser/OS setup. WebView2 does not implement background push. See [notification operation and limits](docs/notifications.md).
