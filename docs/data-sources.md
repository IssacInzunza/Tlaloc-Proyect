# NOAA data sources and verified access

Research and actual HTTP checks: **2026-10-17**. This file records the selected products and alternatives so the investigation need not be repeated on resume. Documentation links below describe upstream services; timestamps and validity are still checked on every observation.

## Sources compared

| Source | Representation and cadence | Access/history | Decision |
| --- | --- | --- | --- |
| NEXRAD Level II | Radar volumes with reflectivity, Doppler radial velocity and polarimetric moments; scan strategy changes resolution and cadence, commonly several minutes | NOAA NCEI/NODD; current archive bucket `unidata-nexrad-level2`, real-time chunks in `unidata-nexrad-level2-chunks` | Evaluated, catalog verified; no per-site volume decoder in 1.0. It requires polar geometry, site selection, beam/terrain treatment and volume QC. |
| NEXRAD Level III | Site-specific derived products with product-dependent resolution, ranges and scan cadence | NCEI historical products and `unidata-nexrad-level3` | Evaluated, catalog verified; not used as a numerical substitute for a gridded MRMS field. |
| MRMS PrecipRate | GRIB2 gzip, nominal two-minute updates; the verified CONUS grid is 7000×3500, 0.01° spacing from approximately 130°W–60°W and 20°N–55°N | Anonymous `noaa-mrms-pds` S3 catalog; recent CONUS NCEP HTTPS fallback | Primary quantitative field: estimated mm/h, not measured gauge rain and not dBZ. |
| MRMS ReflectivityAtLowestAltitude | GRIB2 gzip, nominal two-minute updates, reflectivity dBZ | Same public catalogs; height suffix `00.50` | Optional auxiliary trend. Nearest observation within 90 s, never exact dBZ-to-rain conversion. |
| MRMS RadarQualityIndex | GRIB2 gzip, nominal two-minute product; dimensionless index | Same public catalogs; height suffix `00.00` | Optional quality field. Nearest within 90 s; no quality data means quality unknown, not automatically good. |

MRMS is often described as nominal 1 km resolution. The verified latitude/longitude grid is angular; physical pixel size varies with latitude. Tláloc resamples onto a 1 km **output** meter grid and does not claim to improve native resolution.

Primary documentation:

- [NSSL MRMS project](https://www.nssl.noaa.gov/projects/mrms/)
- [NSSL product table, units, missing and no-coverage codes](https://www.nssl.noaa.gov/projects/mrms/operational/tables.php)
- [MRMS QPE build timeline](https://inside.nssl.noaa.gov/mrms/build_timeline/)
- [NSSL explanation of RQI and radar coverage](https://www.nssl.noaa.gov/about/events/review2021/presentations/NSSL2021LabReviewMRMS.pdf)
- [NCEI NEXRAD access and product descriptions](https://www.ncei.noaa.gov/products/radar/next-generation-weather-radar)
- [NOAA NODD datasets](https://www.noaa.gov/nodd/datasets)
- [MRMS public S3 registry](https://registry.opendata.aws/noaa-mrms-pds/)
- [NEXRAD public S3 registry and Level II migration notice](https://registry.opendata.aws/noaa-nexrad/)

## Actual requests and decoding

These are **verified request patterns**, not hypothetical endpoints:

```text
https://mrms.ncep.noaa.gov/2D/PrecipRate/
https://mrms.ncep.noaa.gov/2D/PrecipRate/MRMS_PrecipRate.latest.grib2.gz
https://mrms.ncep.noaa.gov/2D/ReflectivityAtLowestAltitude/
https://noaa-mrms-pds.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=10
https://noaa-mrms-pds.s3.amazonaws.com/?list-type=2&prefix=CONUS/PrecipRate_00.00/20261017/&max-keys=2
https://unidata-nexrad-level2.s3.amazonaws.com/?list-type=2&prefix=2026/10/17/KYUX/&max-keys=1
https://unidata-nexrad-level3.s3.amazonaws.com/?list-type=2&max-keys=1
```

Anonymous MRMS listing returned CONUS, ALASKA, HAWAII, CARIB and GUAM prefixes, among others. A trial prefix without the product-height suffix returned zero objects; production uses the verified `<region>/<product>_<height>/<YYYYMMDD>/` structure. NEXRAD Level II returned a KYUX object; Level III returned an archive object. Those checks verify access, not per-site decoding or complete retention.

The NCEP sample was genuinely decoded by rasterio/GDAL: `GRIB_ELEMENT=PrecipRate`, `GRIB_UNIT=[mm/hr]`, actual valid time in Unix seconds, 3500×7000 grid. Its finite values included **-3** no coverage, **0** observed dry, and positive rate estimates. The product table also specifies **-1** missing. Both negative rate sentinels are masked to NaN. Reflectivity's **-99** missing and **-999** no-coverage values are unavailable; neither becomes a clear-sky observation.

Eleven S3 PrecipRate observations and contemporaneous reflectivity/RQI were cropped for the bundled episode. The NPZ contains processed, georeferenced data, not original national fields. All actual source URLs, UTC times and the processed-file SHA-256 are stored in `samples/episode.json`. The opt-in integration test downloads one newly cataloged NOAA object and checks the embedded timestamp against its key.

## Availability, latency, archive and limits

No credentials or paid infrastructure are used. Public data downloads have no required account charge for this application; network traffic, local storage and CPU/RAM remain indirect costs. NOAA does not guarantee a personal application's availability or timeliness. Nominal two-minute product generation is not a promise of two-minute end-to-end alert latency. File keys, embedded valid times and observation age are checked; estimates stop for old data. Catalog publication times may lag observation time by several minutes, and products can be missing.

NCEP is a short rolling recent catalog, not the historical source. S3 historical objects are requested only when present. Archive retention and regional product availability are not assumed from an old dataset description. The replay period is 2–60 minutes and samples at most 18 actual observations. No massive archive scan or whole-bucket download is performed.

MRMS regional support is selected by broad product-domain bounds, not country boundaries. Actual pixel validity and quality determine whether a selected circle can be analyzed. Only CONUS file decoding was exercised here; the other listed domains still need real GRIB integration tests, particularly longitude handling near the antimeridian. Tláloc makes no claim of worldwide radar coverage or uniform coverage in Mexico/Canada. An overlapping domain is tried when the first domain has insufficient actual data. No geometric radar range circle is treated as proof of ground-level coverage.

## Mapping and place search

- Map data and tiles are © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). The standard `https://tile.openstreetmap.org/{z}/{x}/{y}.png` endpoint follows the [OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/): visible attribution, normal browser caching and referer, only visible-map requests, no bulk/offline downloader. A CSS filter darkens the tile layer separately from the radar. The initially tested CARTO endpoint rendered API-key-required tiles despite returning images; visual inspection caught this and it was replaced before delivery.
- Address search/suggestions now use [Photon's official API](https://github.com/komoot/photon/blob/master/docs/api-v1.md), backed by OpenStreetMap. Its [public demo policy](https://github.com/komoot/photon#demo-server) permits reasonable use and explicitly supports search-as-you-type, with no availability guarantee. Requests are debounced, limited to one upstream request per second and briefly cached in bounded process RAM. No address queries are written to disk. Browser consent gates external traffic. `TLALOC_ADDRESS_GEOCODER` changes the endpoint. The former Open-Meteo city-only geocoder was removed because it did not find streets/neighborhoods.
- The public Nominatim service is **not** integrated. Its [usage policy](https://operations.osmfoundation.org/policies/nominatim/) was reviewed; using a separate geocoder avoids implying blanket permission for generic generated geocoding services.

NOAA requests attribution and disallows implying endorsement. Tláloc labels transformed fields as processed estimates. Map/service licenses are independent of the repository's MIT source-code license.

## Mexicali display correction and measured product differences

The user reported a blank rain layer despite an external echo image. Exact external timestamp/product could not be established from that screenshot alone. We independently checked public NOAA observations at 2026-10-17 19:18, 19:20 and 19:22 UTC in a local Mexicali crop. PrecipRate was zero; ReflectivityAtLowestAltitude had no finite values. This was actual upstream field content, not a NaN-to-zero conversion in the renderer.

At **19:20:41 UTC**, `MergedReflectivityQCComposite` contained echoes: 26.5 dBZ maximum, 10,511 pixels ≥5 dBZ and 63.7% finite pixels over the entire radius+margin crop. It is the maximum reflectivity through a vertical column; it does not establish surface rainfall. The low-level composite and non-QC composite also contained different fields. The non-QC field was inspected diagnostically and is **not** the shipped default.

The map now prefers genuine QC composite reflectivity for display, alongside a distinct PrecipRate layer. Composite files use the verified public path `CONUS/MergedReflectivityQCComposite_00.50/<YYYYMMDD>/MRMS_MergedReflectivityQCComposite_00.50_<timestamp>.grib2.gz`. Metadata retain each layer's own timestamp/source/unit/statistics. If the composite is absent, available low-altitude reflectivity is shown under its own name; no missing echo is invented. Existing rain tracking/alerts still use the rate field and low-altitude trends.

Photon returned genuine Calle Naranjos and Avenida de los Naranjos features for the reported place query in a consent-authorized verification. This verifies these mapped streets, not the completeness or precision of arbitrary house addresses.
