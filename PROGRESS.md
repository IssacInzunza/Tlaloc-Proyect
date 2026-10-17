# Tláloc Project progress

## Current phase
Photon/default-layer preferences and background rain notifications implemented and integrated. Tests passed; real OS notification delivery remains a user-browser activation check, not a claimed result.

## Latest delivery: notifications and preferences (2026-10-17)
- User requested Photon always active, precipitation as initial radar layer, browser-local persistence of selected layer, explanation of cold loading (no optimization), then rain notifications outside the page.
- Contracts and exclusive responsibilities defined before delegation. Real backend, frontend and scientific-review specialists worked independently; main integrated API/lifespan/actual target rate, resolved levels contract and hidden-panel CSS conflicts, and executed integrated checks.
- Photon is always enabled in UI under the user’s prior explicit authorization. Old addressConsent=false preferences no longer disable it. API external=true retained as deliberate upstream-use flag; queries remain bounded RAM-only.
- Precipitation is the initial selection. Browser LocalStorage tlaloc.radarLayer restores selected rate/reflectivity; absent selected products display an honest unavailable message. Last live location remains browser-local and replay temporary.
- Opt-in Web Push implemented: explicit enable permission gesture, test/disable/status controls, root service worker, local persisted subscription/VAPID/watch, background worker every120s, same-origin writes, allowed push endpoints, encryption and no coordinates in payloads. Server and computer must stay on. Pausing map does not stop push; disable explicitly stops watch.
- Scientific gates: actual target PrecipRate onset only, valid target/good RQI/recent nonfuture observations, confident selected arrival forecasts, no display-only echo alerts, persistent wet latch, retry/deduplication and reset on watch change. No replay notifications.
- Browser watch preferences remain LocalStorage; enabling background notifications additionally stores the watched point on this same computer so the local server can operate after tab closure. No remote watch database/accounts/paid service.
- VERIFIED: full backend138passed/1 opt-in NOAA network testskipped (8.55s), notification29testsincluded; frontend9unitpassed; production TypeScript/Vitebuildpassed; Ruffpassed; Edge11E2Epassed (42.6s). E2E covers actual NOAA sample, preference persistence, Photon debounce/retry and mocked push lifecycle/denied permission/replay isolation, plus real localhost service-worker registration without requesting notification permission.
- A first integrated E2E run failed because settings-panel display:flex overrode hidden. Main moved styling into a child; full rerun11passed. Tests also caught contract mismatch with default three selected levels; backend now accepts all selected levels including empty and suppresses informational forecast pushes.
- Real browser push subscription/transport/desktop presentation NOT verified and no real push sent. User must activate and test in full Edge/Chrome. WebView2 Push Notifications is documented as unimplemented; UI explains unsupported/failed subscription. Passing mocks or service-worker registration does not prove desktop delivery.
- Cold-load explanation: initial actual four-product/six-frame NOAA analysis measured43.553s. Listings/downloads/decompression of national GRIBs then local reprojection/tracking/rendering dominate; later local caches reduce downloads. No performance optimization made in response to the question.
- Current server: http://127.0.0.1:8000, uvicorn33160, execsession40774, --no-access-log. Health and push config verified live (enabled/publickey87chars; no secret output). Build419.37kB JS/130.17kB gzip. No commit/push/deployment.

### Exact next step if interrupted or resumed
1. Refresh http://127.0.0.1:8000 (Ctrl+F5). Current server33160 serves final build/backend; if stopped run scripts/run.ps1.
2. To finish delivery verification, open this same URL in full Edge/Chrome, open Settings, Enable rain notifications, accept browser permission and Send test notification. Verify actual OS appearance, including with tab closed. Do not claim real delivery before this check or repeat approved address queries/NOAA downloads without reason.
3. Existing tests are complete; rerun only after relevant changes. Scientific calibration/additional historical episodes remain pending as described below. Web Push does not monitor while the computer/server are off.

## Earlier corrective record (before latest delivery, 2026-10-17)
- User reported `naranjos mexicali` not found, no autocomplete, blank radar versus external image, last location not restored and preference must stay local.
- Contracts and exclusive ownership added to `docs/contracts.md` before delegating three real subagents (address backend, frontend/persistence, scientific layer tests).
- Confirmed old geocoder was city-only Open-Meteo. New Photon adapter implemented; 24 fixture tests pass. Exact street example was independently checked by agent and returned actual Calle Naranjos/Avenida de los Naranjos features; not a guarantee of house-level mapping.
- Main tool's first Photon query was rejected by approval review for address privacy. Agent's independently approved call occurred before the rejection was propagated. User was informed and then explicitly authorized Photon external address search. No further unapproved address calls were made.
- New API requires `external=true` before Photon contact; frontend explicit consent remains browser-local. Suggestions use debounce, independent rate limit, short bounded RAM cache, no query files. Actual integrated API returned Centro de Desarrollo Humano Integral Los Naranjos, Avenida de los Naranjos and Calle Naranjos in Mexicali.
- The live watch stays in browser LocalStorage. Replay/sample positions are temporary. Browser regressions and a real street-selection/reload check both verified restoration, including edits while monitoring is paused.
- Added actual separately georeferenced `layers.rate` (mm/h) and `layers.reflectivity` (dBZ), actual auxiliary timestamps, native-grid statistics and distinct no-data masks. Legacy rate overlay retained. Twelve scientific/causal layer tests pass.
- Actual NOAA comparison for screenshot time 19:18,19:20,19:22 UTC: rate all0, lowest-altitude reflectivity missing. QC composite at19:20:41 had max26.5dBZ,10511pixels>=5dBZ,63.7%finitecrop. Shipped display now separately fetches QC composite, never raw non-QC or synthesized rainfall.
- Actual integrated LIVE API after correction returned six frames, QC composite max28dBZ and11118echo pixels with64.9%finitecrop. Server calculation43.553s on initialfour-productload. Distinguish rate-analysis coverage from selected-layer coverage in UI.
- Added causal auxiliary selection/guards: rain trends and RQI never use timestamps later than the historical issue time. Replay rendering also excludes future auxiliary layers; no future-to-past display leak.
- Backend: **109 passed, 1 opt-in network test skipped**. Ruff passed. Frontend: **5 unit tests passed**, final production build passed. Browser: **6 mocked corrective regressions passed**, plus **1 actual NOAA sample E2E passed** separately. Automatic layer selection now uses the current frame's available fields; a manually selected missing layer shows an explicit message.
- Main owns shared API/types/radar/docs. Current server on8000 is process35132(session23452), no HTTPaccesslogging.
- Actual integrated live browser verification COMPLETED: genuine QC composite max28dBZ,10835echo pixels,6liveframes; genuine Photon street options; selected street watch persisted across reload; zero page runtime errors. Visually inspected `.cache/browser/mexicali-corrected.png`: actual Mexicali geographic map, blue/green radar echoes and real Naranjos dropdown results. Not fixture data.
- Final frontend bundle: 408.94 kB JS /126.78 kB gzip. Search retries HTTP 429 at most three times with cancellable 1.1/2.2/4.4 s backoff. Initial ArrowUp selects the last result correctly.
- The original sample E2E expected the rate timestamp 08:20, but the selected causal reflectivity product was observed at 08:18:37. The assertion now checks the actual selected product timestamp; final rerun passed in 12.1 s. Replay does not substitute a later observation or fake its time.

### Previous delivery instructions (superseded above)
1. Use http://127.0.0.1:8000 and refresh the existing page (Ctrl+F5). Current server35132 has the final backend and serves the final build; restart with scripts/run.ps1 if stopped.
2. All corrective verification is complete. Do not repeat approved address queries or NOAA downloads without a new reason. Browser-local preference storage requires the same browser/origin; private sessions can discard it.
3. Future work retains these limits: address-map completeness, composite echoes not proving surface rain, rendering limited to the watch region, and uncalibrated nowcasting confidence. See docs/limitations.md. No commit, push or deployment was performed.

## Prior implementation log (before this corrective report)

## Completed investigation
- Repository inspected: only an initial README and Git attributes existed.
- NSSL MRMS product tables and NOAA NCEI NEXRAD documentation reviewed.
- Live NCEP HTTPS directory returned 200 on 2026-10-17.
- Anonymous MRMS S3 ListObjectsV2 returned actual region prefixes.
- A real MRMS PrecipRate GRIB2 gzip was downloaded for decoder verification.
- NEXRAD Level II migration to `unidata-nexrad-level2` verified in the AWS registry.

## Decisions
- Local FastAPI + React/TypeScript/Leaflet application, without commercial services.
- MRMS quantitative precipitation rate as the primary field. Units are estimated mm/h, never dBZ.
- Decode GRIB2 with rasterio/GDAL; reproject only a small local region into azimuthal equidistant meters.
- Conservative coverage gating; missing data must never become dry weather.
- Region tracking and geometry advection, no generative model or Doppler velocity substitution.

## Multi-agent integration
- Contracts and exclusive file ownership recorded in `docs/contracts.md` before delegation.
- Frontend specialist: map/dashboard/i18n/replay/settings implemented; build and five frontend tests verified. Main owns final integration.
- Tracking specialist: scientific review completed; 22 deterministic tests passed.
- Replay/validation specialist: prefix isolation and honest censored metrics implemented; 18 deterministic tests passed; technical docs corrected to English.
- Main agent: MRMS provider, GRIB decoder, RQI coverage, API, history, real sample capture and integrated checks.

## Implemented
- React/TypeScript/Leaflet bilingual dashboard with live API and actual NOAA replay; marker drag, radius, language persistence and responsive layouts verified in the browser.
- Bounded public NOAA MRMS S3 catalogs with NCEP live fallback, decompression validation, local cache and cleanup.
- Actual PrecipRate, reflectivity and RQI decoding; NaN missing values distinct from observed zeros.
- AEQD meter grids, geographic PNG overlays, actual observation times and conservative coverage.
- Connected components, association with phase correlation prior, footprint advection, heuristic ETA intervals.
- SQLite alert lifecycle scoped to coordinates/radius/threshold, deduplication and suspension on unavailable data.
- Prefix-only replay and experimental metrics, bounded stored comparison summaries.

## Verified real observations
- `samples/episode.npz` + metadata: 11 genuine NOAA MRMS observations, 2026-10-17 08:00–08:20 UTC at 27°N, 82.5°W, radius 50 km. Processed/cropped data, not synthetic.
- Sample compressed size after RQI/reflectivity: 282,046 bytes; original URLs and SHA-256 retained in `samples/episode.json`.
- Actual latest sample coverage: valid fraction 1.0, target valid, `radar_quality_good`.
- Offline replay of real sample executes; no arrival events at this selected target, so arrival/trajectory error metrics are null. This does not establish forecast accuracy.

## Tests and environment issues
- Initial full suite: 49 passed, 1 network test skipped, 19 setup errors from sandbox TEMP access. These were fixture directory errors, not application assertions.
- Windows sandbox also blocked asyncio's internal loopback socketpair; tests hung before any application endpoint executed. Six identified old pytest processes were closed after confirming their command lines.
- An escalation attempt was not executed because automatic approval review hit the account usage limit. On the user's `continua`, review/execution resumed successfully; no bypass was used.
- Latest complete backend suite: **71 passed, 1 opt-in network test skipped** in 7.04 s, using `.cache/pytest-release` outside the socket-restricted sandbox. Cache-age regression included.
- Separate real NOAA network integration: **1 passed**, decoding a recent public S3 observation and validating the embedded timestamp.
- Frontend Vitest: **5 passed**. TypeScript + Vite production build passed; JS bundle approximately 401 kB (124 kB gzip).
- Real bundled sample HTTP replay verified with zero provider downloads; 11 frames, RQI good, exact source timestamps and matching SHA-256.
- Ruff checks passed after import/style corrections.
- Browser E2E previously passed the complete language/radius/replay/mobile flow (7.3 s), but visual inspection caught CARTO API-key-required placeholder tiles. Replaced CARTO with standard OpenStreetMap, preserved attribution, and filtered only the tile layer for dark styling.
- An expanded actual-marker-drag test caught React/pan updates interfering with the gesture. Stable target icon/coordinate identity and immediate recenter fixed the interaction.
- **Final actual-browser E2E passed** (6.0 s total, 4.3 s scenario): unsupported location handling, radius change, coordinate editing, actual marker drag, language persistence across reload, real NOAA sample replay, matching timeline/predictions, loaded OSM tiles and mobile width.
- Final desktop/mobile screenshots visually inspected: actual geographic labels and tiles, correct radar overlay, readable panels and no horizontal mobile overflow. Local review images are `.cache/browser/desktop.png` and `mobile.png`.
- Production build after all frontend fixes passed (400.81 kB JS /123.97 kB gzip; 31.00 kB CSS /10.55 kB gzip). No external font service is loaded.
- Real city search returned actual localized Mexicali results from Open-Meteo/GeoNames.
- Real live Mexicali radar query: six frames, valid area 1.0, target valid, RQI good, no precipitation above threshold. First load 19.759 s backend /20.044 s HTTP; server working set 114.5 MiB and peak 393.7 MiB. Snapshot saved locally at `.cache/live-validation.json`.
- Local server running at http://127.0.0.1:8000, process 37800 (uvicorn, session 75342). Measured initial working set approximately 91 MB before national radar decode.
- Dependencies installed in project `.venv` using Python 3.12.14 and frontend `node_modules`; no paid services. Exact installed backend versions saved in `backend/requirements.lock.txt`.

## Documentation and operation
- Main English README and Spanish translation, MIT license, Windows/Linux run scripts, source research, architecture, processing, tracking, nowcasting, testing and limitations now exist.
- No commit/push/deployment performed. Preserve the user-provided `.github/instructions/commit-message.instructions.md`.

## Remaining scientific and platform work (not claimed complete)
- Confidence/arrival interval calibration and a diverse independent historical evaluation are not done. The real bundled example has no verifiable target onset; no accuracy claim follows from passing tests.
- Numeric ETA intervals are intentionally restricted to sufficiently supported 0–30 min arrivals. Geometry is evaluated through 60 min, but 30–60 min outputs remain uncertain without a precise interval.
- Only CONUS/Mexicali ingestion received actual GRIB integration verification. Other MRMS domains, polar/dateline behavior and Linux operation require additional field/platform verification.
- NEXRAD Level II/III catalogs were verified, but individual-radar decoding/fallback is not implemented.
- Broad/clipped systems, ambiguous splits/merges and weak registration remain informational. No physical prediction of unformed storms, calibrated probabilities or certified warnings.
- One nonfatal upstream Starlette/httpx deprecation warning remains in the test suite. All assertions pass; a future transport update can remove it.
- Background push was subsequently implemented under the explicit extension above. Monitoring with the computer or local server stopped remains unavailable.

## Exact next steps if interrupted
1. Read this file and `docs/contracts.md`; do not repeat source research or sample downloads.
2. Use the running loopback server at http://127.0.0.1:8000; if stopped, run `powershell -ExecutionPolicy Bypass -File scripts/run.ps1` from the repo (dependencies/build already exist).
3. Delivery verification is complete: backend 71 passed +1 separately passed network test, frontend 5 passed, browser E2E 1 passed, production build/Ruff passed. Rerun only after relevant changes.
4. For further development, prioritize independently annotated historical arrivals, uncertainty calibration, additional real MRMS-domain tests and optional site-specific NEXRAD integration.
