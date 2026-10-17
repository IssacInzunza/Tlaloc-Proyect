# Testing and validation

## Integrated verification on Windows 11

The latest backend run after the address/radar/persistence correction reported **109 passed, 1 opt-in network test skipped**. A separate earlier run with `TLALOC_NETWORK_TESTS=1` passed the real NOAA GRIB integration test. Frontend Vitest reported **5 passed**, and TypeScript/Vite produced the production bundle. No operational forecast accuracy is inferred from these software checks.

The API suite includes two tests using the genuinely observed bundled NOAA episode: checksum and georeferencing validation, plus an HTTP replay which asserts that no upstream download occurs. It also exercises query/date/radius validation, provider failure, location-scoped cache/history, alert deduplication and data-age rechecking inside the result cache.

The browser integration test (`frontend/e2e/app.spec.ts`) drives the real local server, without substituting radar observations. It checks a globally selectable unsupported location, radius, coordinate editing, marker drag, language persistence, real sample replay, frame-matched predictions, loaded public OpenStreetMap tiles and a 390 px mobile layout. Screenshots are written under `.cache/browser/` for visual inspection. Initial screenshot review caught API-key-required CARTO tiles and caused their replacement with OSM; successful image loading alone would not have established correct map content.

Six additional browser regression tests in `corrections.spec.ts` use explicitly mocked fixtures to isolate local live-watch persistence across replay/reload, consent-gated debounced address suggestions, keyboard control, bounded/cancelled 429 retries, distinct radar units, automatic per-frame layer selection and mobile layout. All six passed; their fixture screenshots are UI checks, not proof of NOAA observations.

A separate real integrated browser verification used actual Photon results for the user-authorized Mexicali street query and actual live NOAA composite reflectivity. It confirmed returned street options, a visible composite radar image (28 dBZ maximum, 10,835 cropped-grid echo pixels during that check), no browser runtime errors and restoration of the selected watch after reload. The local review image is `.cache/browser/mexicali-corrected.png`. The older city-only geocoder failure was genuine and has been replaced, not hidden with synthetic search results.

Auxiliary observation timestamps are independently preserved. Tests assert that future low-altitude reflectivity cannot alter segmentation trends, future RQI cannot certify/suppress earlier forecasts, and replay display layers never exceed the historical issue time. Composite reflectivity is display-only: an echo with zero rate must not create a rain-arrival alert.

Start the production server on loopback port 8000 before running `npm run test:e2e` in `frontend`. Windows uses installed Edge; other platforms use Playwright Chromium by default. Linux execution has not been verified in this session. Screenshots, caches and local test artifacts are excluded from Git.

## Offline local checks

From the repository root, after installing `backend/requirements.txt` in `.venv`:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_replay.py -q --basetemp=.cache/pytest-replay
.venv/Scripts/python.exe -m pytest backend/tests -m "not integration" -q --basetemp=.cache/pytest-offline
```

The workspace-local temporary directories also work in environments that restrict access to the default system TEMP directory. Do not run concurrent suites with the same `--basetemp` directory.

Replay tests use small deterministic fields exclusively as fixtures. They are not NOAA observations, historical episodes, or operational performance estimates. They verify temporal isolation, strict ordering, actual timestamps, multiple regions, censoring, missing coverage, missed onsets, ongoing rain, data availability, and geodesic centroid displacement. `predict` receives only `frames[:index+1]` and the timestamp of that observation. Future verification occurs after all predictions have been constructed and never calls `predict` again.

## Replay metric definitions

The reference is the target radar pixel, using the same precipitation threshold as the forecast. It is neither a rain gauge nor confirmation of surface rainfall. NaN means unknown; zero means observed dry.

- An observable onset requires a valid dry pixel followed by a valid wet pixel, no more than 5 minutes apart. The actual onset lies within that interval. An onset is not inferred at the beginning of an already wet episode or immediately after an unknown observation.
- Each forecast with an arrival interval is evaluated separately. It is compatible when its interval intersects the interval between the last dry and first wet sample. No arbitrary tolerance is appended to the predicted interval.
- `arrival_mae_minutes` compares the midpoints of the two intervals, exclusively for compatible hits. `mean_lead_minutes` uses the midpoint of the observed interval relative to forecast issuance. These are approximations conditional on hits, not scores for all forecasts or precise arrival times.
- `false_alarm_forecasts` requires observations covering the forecast horizon. An incomplete horizon, NaN, or gap exceeding 5 minutes causes censoring. The 5-minute limit is a conservative evaluation choice, not a calibrated parameter. An observed compatible hit within a partial horizon can be scored because the event has already occurred; later missing coverage does not erase it.
- Forecasts issued while the target is wet or unknown are counted separately as `ongoing_rain_forecasts` or `unknown_target_forecasts`; they are not successful new arrivals.
- `missed_onsets` counts observable onsets without a compatible prior forecast. A subsequent episode requires an intervening dry observation. Counts describe this episode, not climatological frequencies. Multiple regional forecasts may verify against the same target onset: forecast counts and event counts are not interchangeable and do not independently define POD/FAR/CSI.
- `trajectory_mae_km` is the geodesic error of the centroid extrapolated to the next observation at its actual timestamp, only when the tracker retains the identity and a valid motion association. It also includes regions without a predicted arrival. With no verifiable associations it is `null`, with `trajectory_samples=0`. The tracker's own association is not an independent trajectory annotation.
- `target_data_availability` is the fraction of received samples with a finite target pixel. It is not the provider's temporal availability or coverage of the entire area. An empty dataset produces `null`; `verification_gap_count` identifies gaps exceeding 5 minutes.
- `processing_seconds` measures the entire local evaluation, including optional image generation. It excludes downloads and provider publication latency. Runs with and without images are not directly comparable.

The temporal scheme uses all available earlier frames, with the provider bounding their total count. It does not use a moving window that would artificially change track identities.

## Real observations and network checks

NOAA downloading and decoding, integration tests marked `integration`, and replay of real episodes must be recorded separately from offline tests. Running `pytest` with fixtures does not confirm NOAA access, product availability for a location, or scientific performance in real storms. For network tests, consult the explicit enablement option in the integration test files and run only when configured; do not substitute synthetic data for failures.

A real episode must retain source URLs and observation timestamps. Scientific comparisons require independent and diverse episodes, complete horizons, surface references where possible, and uncertainty analysis. Current metrics are experimental diagnostics, not calibrated probabilities or operational validation.
