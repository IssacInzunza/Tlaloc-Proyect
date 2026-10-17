# Integration contracts and ownership

## Shared observation contract
- `Location`: WGS84 `lat` [-90,90], `lon` [-180,180], `radius_km` [10,100] default 50, precipitation `threshold` [0.1,10] default 0.2 mm/h.
- `Frame` (`backend/app/radar.py`): aware UTC `time`, bounded 2D float32 `rate` in estimated mm/h, NaN for missing/no coverage; AEQD CRS centered on target, north-up raster affine, spacing in meters; `source` is actual public object URL. Optional simultaneous `reflectivity` in dBZ with NaN for missing.
- A zero rate is observed dry; NaN is never dry. Prediction must stop at stale >10 min, invalid target, or <60% valid circle.
- `Prediction` schema in `backend/app/models.py` is the authoritative API contract. Coordinates `[lat,lon]`. Direction is clockwise from north, motion toward direction. No calibrated probabilities.
- `arrival_minutes` is a heuristic uncertainty interval relative to the evaluation timestamp; use footprint geometry, never only centroid. No future observations in prediction construction.
- Coverage states: `available`, `partial_coverage`, `insufficient_coverage`, `provider_unavailable`, `stale_observations`, `no_precipitation_detected`. Quality: `radar_quality_good`, `radar_quality_limited`, `product_mask_only`. Optional `Frame.quality` is actual aligned RQI. No quality flag certifies surface rainfall or beam visibility.

## HTTP contract
- GET `/api/analysis?lat=...&lon=...&radius_km=...&threshold=...`: `Analysis` typed in `frontend/src/services/api.ts`. All frames carry PNG data URI, geographic bounds, aware timestamp, source, coverage. Analysis predictions correspond only to latest observation.
- GET `/api/search?q=...&language=en|es`: `{name,lat,lon}[]`; explicit submitted search only.
- GET `/api/history` with location query: `{time,action,alert}[]`, action created/updated/cancelled/suspended.
- POST `/api/replay`: Location + aware `start`, `end`, optional `sample`; bound to 2–60 minutes. Response `Replay` type in frontend service. Up to 18 actual observations, prefix-only predictions, future validation separately.
- GET `/api/sample`: actual bundled episode metadata `{location,frames:[{time,source}],...}`.
- GET `/api/runs`: stored metric summaries for comparison. Nullable metrics mean unmeasurable, never zero error.
- Errors: structured HTTP errors with stable English detail code translated in UI. UI must clear old location observations on location/radius change.

## Parallel ownership
- Main agent: NOAA provider, radar decoding/coverage, models, API, history, shared service types/configuration, overall integration, data sample, repository docs, PROGRESS, dependency installation and execution.
- Frontend specialist: `frontend/src/App.tsx`, `frontend/src/components/**`, `frontend/src/styles.css`, `frontend/src/i18n/en.json`, `es.json`, frontend tests. Do not change shared types without notifying main agent.
- Tracking specialist: `backend/app/tracking.py`, `backend/app/nowcasting.py`, `backend/tests/test_tracking.py`, `docs/tracking-algorithm.md`, `docs/nowcasting.md`. Scientific review and fixes; preserve public function contracts (`predict` supports optional `tracked_regions`).
- Validation specialist: `backend/app/replay.py`, `backend/tests/test_replay.py`, `docs/testing.md`. Review scientific metrics and chronological isolation; add meaningful deterministic replay tests. Report API/storage/coverage findings to main agent instead of editing their files.

All specialists must report implemented versus actually verified work. Main agent runs integrated checks and resolves incompatibilities. No deployment or external messaging.

## Corrective work: address search, radar layers and local location (2026-10-17)

- Search remains GET `/api/search` returning `{name,lat,lon}[]`, optionally with `kind` and `provider` strings. Optional `lat`, `lon` provide approximate ranking; `suggest=true` enables debounced suggestions. Explicit `external=true` consent is required before upstream contact (403 otherwise). Photon supports search-as-you-type; public Nominatim must never receive autocomplete traffic. Queries stay in bounded RAM cache, never disk. Never invent an address coordinate.
- Radar retains legacy rate `image/bounds/time/source/coverage`. Optional `layers`: `{rate: RadarLayer, reflectivity?: RadarLayer}`. Each layer has `image`, `bounds`, `time`, `source`, `unit`, optional `product`, `valid_fraction`, nullable `max_value`, and `echo_pixels`. QC composite reflectivity is a separate display field; low-altitude reflectivity remains separate for causal trends. No echo differs from no data. Precipitation is the initial selection; the selected layer persists locally with an honest missing-layer message when absent. Layer time/source/unit/legend always match the selected product. Historical display and analysis exclude future auxiliary observations.
- Last watch location/preferences belong in browser LocalStorage only. Historical replay/sample location is temporary and must not overwrite the saved live watch. Restoring live mode or reloading restores the last live watch. Server history may remain local for the present correction, but API analysis should not create server-side saved watch preferences.
- Ownership for this correction: main owns radar/provider/main/API/types/docs/PROGRESS and integrated execution; address specialist owns only new `backend/app/geocoding.py` + `backend/tests/test_geocoding.py`; frontend specialist owns App/components/styles/i18n and its tests; scientific reviewer owns only new `backend/tests/test_radar_layers.py` and reports scientific/provider findings, no edits to main-owned files.

## Notifications and preferences extension

The user requests Photon always enabled, precipitation as initial layer with selected layer persisted in browser LocalStorage, and rain notifications when outside the web page. Photon/default-layer edits are main-owned and already written. Do not optimize first-load radar performance: the user requested an explanation only.

Notifications use standard Web Push + a service worker so delivery can occur after tab closure. The local backend/computer must remain running; browser/OS must allow push delivery. Browser notification permission is requested only by an explicit Enable button. No accounts or paid services. Subscription/key/watch data live only in this computer's ignored cache; encrypted notification messages travel via the browser's push service. No exact watched coordinates/address in notification payloads. Alert confidence rules remain unchanged.

API contract: GET `/api/notifications/config` returns `{public_key:string,enabled:boolean}`; POST `/api/notifications/subscribe` accepts `{subscription:{endpoint,keys:{p256dh,auth},expirationTime?},location:Location,language:'en'|'es',levels:string[]}` and returns `{id:string,enabled:boolean}`. Subscription ID is a capability secret saved browser-locally. POST `/api/notifications/{id}/update` updates `{location,language,levels}` (only live watch); GET `/api/notifications/{id}/status` returns `{enabled,last_checked,last_sent,last_error}`; DELETE `/api/notifications/{id}` stops subscription; POST `/api/notifications/{id}/test` sends a clearly labeled test notification. Fixed API routes must be registered before static frontend. Same-origin mutations and bounded subscriber count/interval required. Validate endpoint against actual public browser-push providers to avoid arbitrary network targets.

Main supplies `analyze(Location)->dict` callback. Result includes existing coverage/predictions, observation_time and new nullable `target_rate` for actual radar-estimated rain at target. Notify observed wet onset or sufficiently confident preventive/imminent arrivals; deduplicate across polls, do not notify for unavailable/stale data or display-only reflectivity. No replay notifications. Background service has explicit start/stop lifecycle, persists only locally, and resumes enabled local watches while server runs.

Ownership: notification backend specialist owns `backend/app/notifications.py`, optional `backend/app/notification_locales/*`, `backend/tests/test_notifications.py`, and `docs/notifications.md`; frontend specialist owns NEW NotificationSettings component, NEW notification service client, `frontend/public/sw.js`, notification e2e/unit tests, and locale JSON additions. Do not edit App.tsx (main inserts component), main.py (main wires service/router/lifecycle), package/requirements (main installs dependencies). Reviewer may review scientific/delivery failure modes read-only and report findings. Main integrates and verifies. No real push subscription payload/key should be printed in logs or committed.
