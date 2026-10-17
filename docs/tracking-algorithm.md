# Component tracking

Rates are estimated mm/h on an identical local AEQD grid. Eight-connected pixels at or above the requested threshold form components. Components smaller than 2 km² are removed; only the largest 100 are tracked to bound noisy-field work. This can omit small or weak echoes and is not a hydrometeor classification.

Motion uses actual observation intervals, accepted from 30 to 600 seconds. A different grid, reversed/duplicate time, a longer gap, or less than 60% common finite raster coverage prevents motion estimation. Missing pixels are never interpreted as observed dry weather.

Log-rate phase correlation supplies a translation prior. Its response must be at least 0.08 and speed at most 55 m/s; failed registration produces `motion_uncertain`, never a fabricated zero velocity. This response is an engineering diagnostic, not a probability. Stationary textured echoes can still yield valid zero motion.

Each old footprint is translated once. Candidate pairs require physically bounded centroid separation and either translated overlap or a residual within 3.5 km. Ambiguous many-to-one/one-to-many associations produce merge/split uncertainty without velocity. Accepted one-to-one velocities use centroid displacement in meters divided by actual elapsed seconds. Boundary clipping, missing local coverage, area ratios outside [0.5,2], translated overlap below 0.35, excessive speed, or residual exceeding max(2 pixels,25% global translation) suppress motion. Centroid drift during deformation remains a limitation.

Stable identity persists only through one-to-one matching. Two scans yield medium confidence at sufficient overlap; at least three observations, overlap >=0.65 and velocity change <5 m/s can yield high confidence. Growth/intensity change caps high at medium. Confidence labels are uncalibrated heuristics. Intensity increase uses a >30% and >0.5 mm/h mean-rate increase; weakening uses a >30% decrease. Reflectivity increasing requires >=5 dBZ increase, when available. Neither is evidence of surface rainfall intensification by itself.

An unmatched interior echo is labelled new only when its previous footprint was >95% covered. Edge/missing-coverage echoes remain uncertain; this does not prove physical genesis. Phase correlation assumes coherent regional motion, so opposing cells, developing convection, widespread uniform precipitation, and major deformation may prevent reliable extrapolation.

Deterministic synthetic checks reside only in `backend/tests/test_tracking.py`; production does not generate substitute radar observations.
