"""Validate GRIB2 and reproject a bounded region into physical meter coordinates."""
import base64
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.transform import array_bounds, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from .models import Coverage, Location


@dataclass
class Frame:
    time: datetime
    rate: np.ndarray
    transform: object
    crs: object
    source: str
    reflectivity: np.ndarray | None = None
    quality: np.ndarray | None = None
    reflectivity_source: str | None = None
    quality_source: str | None = None
    reflectivity_time: datetime | None = None
    quality_time: datetime | None = None
    composite_reflectivity: np.ndarray | None = None
    composite_reflectivity_time: datetime | None = None
    composite_reflectivity_source: str | None = None

    def __post_init__(self):
        if self.time.tzinfo is None or self.rate.ndim != 2 or self.rate.size > 300_000:
            raise ValueError("Invalid frame geometry or timestamp")
        if np.any(np.isinf(self.rate)) or np.any((self.rate < 0) & np.isfinite(self.rate)):
            raise ValueError("Negative or infinite rates must be masked")
        if (self.transform.a <= 0 or self.transform.e != -self.transform.a
                or self.transform.b != 0 or self.transform.d != 0):
            raise ValueError("Expected a north-up square meter grid")
        for field in (self.reflectivity, self.quality, self.composite_reflectivity):
            if field is not None and field.shape != self.rate.shape:
                raise ValueError("Auxiliary fields must share the observation grid")

    @property
    def spacing(self):
        return float(self.transform.a)

    def xy(self):
        rows, cols = np.indices(self.rate.shape)
        return (cols + 0.5) * self.spacing + self.transform.c, self.transform.f - (rows + 0.5) * self.spacing

    def to_geo(self, x, y):
        lon, lat = Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True).transform(x, y)
        return lat, lon


def grid(location: Location):
    extent = (location.radius_km + 20) * 1000
    size = int(2 * extent / 1000) + 1
    crs = CRS.from_proj4(f"+proj=aeqd +lat_0={location.lat} +lon_0={location.lon} +datum=WGS84 +units=m")
    return size, from_origin(-size * 500, size * 500, 1000, 1000), crs


def decode(path: Path, location: Location, source: str, reflectivity_path: Path | None = None,
           quality_path: Path | None = None, composite_path: Path | None = None) -> Frame:
    size, affine, crs = grid(location)

    def read_field(field_path, kind):
        # GDAL decodes the packed national field internally; output remains bounded.
        with rasterio.open(field_path) as ds:
            if ds.driver != "GRIB" or ds.count != 1 or not ds.crs or ds.width * ds.height > 100_000_000:
                raise ValueError("Unsupported GRIB geometry")
            tags = ds.tags(1)
            if kind == "rate" and tags.get("GRIB_ELEMENT") != "PrecipRate":
                raise ValueError("Expected PrecipRate product")
            if kind == "quality" and tags.get("GRIB_ELEMENT") != "RadarQualityIndex":
                raise ValueError("Expected RadarQualityIndex product")
            if kind == "reflectivity" and tags.get("GRIB_ELEMENT") not in (
                    "ReflectivityAtLowestAltitude", "MergedReflectivityQCComposite",
                    "LowLevelCompositeReflectivity", "MergedReflectivityComposite"):
                raise ValueError("Expected a supported reflectivity product")
            try:
                timestamp = datetime.fromtimestamp(int(tags["GRIB_VALID_TIME"].split()[0]), UTC)
            except (KeyError, ValueError, OverflowError) as error:
                raise ValueError("Missing or invalid observation timestamp") from error
            if timestamp > datetime.now(UTC):
                raise ValueError("Observation timestamp lies in the future")
            output = np.full((size, size), -9999, dtype="float32")
            # Nonnegative PrecipRate values are estimates; -1 missing and -3 no coverage.
            # Reflectivity -99/-999 are both unavailable, never dry pixels.
            with rasterio.Env(GDAL_CACHEMAX=64):
                reproject(rasterio.band(ds, 1), output, src_transform=ds.transform,
                          src_crs=ds.crs, dst_transform=affine, dst_crs=crs,
                          dst_nodata=-9999, resampling=Resampling.nearest, num_threads=1)
            minimum = -90 if kind == "reflectivity" else 0
            maximum = {"rate": 500, "reflectivity": 95, "quality": 1}[kind]
            invalid = (output < minimum) | (output > maximum)
            output[invalid] = np.nan
            return output, timestamp

    rate, timestamp = read_field(path, "rate")
    refl = None
    refl_time = None
    if reflectivity_path:
        refl, refl_time = read_field(reflectivity_path, "reflectivity")
        if abs((timestamp - refl_time).total_seconds()) > 90:
            refl = None
            refl_time = None
    quality = None
    quality_time = None
    if quality_path:
        quality, quality_time = read_field(quality_path, "quality")
        if abs((timestamp - quality_time).total_seconds()) > 90:
            quality = None
            quality_time = None
    frame = Frame(timestamp, rate, affine, crs, source, refl, quality,
                  reflectivity_time=refl_time, quality_time=quality_time)
    if composite_path:
        composite, composite_time = read_field(composite_path, "reflectivity")
        if abs((timestamp-composite_time).total_seconds()) <= 90:
            frame.composite_reflectivity = composite
            frame.composite_reflectivity_time = composite_time
    return frame


def coverage(frame: Frame, location: Location, now: datetime | None = None) -> Coverage:
    now = now or datetime.now(UTC)
    x, y = frame.xy()
    circle = x*x + y*y <= (location.radius_km * 1000)**2
    valid = np.isfinite(frame.rate)
    fraction = float(valid[circle].mean())
    center = tuple(s // 2 for s in frame.rate.shape)
    target_valid = bool(valid[center])
    age = max(0, (now - frame.time).total_seconds() / 60)
    status = "available"
    quality = "product_mask_only"
    if not target_valid or fraction < 0.6:
        status = "insufficient_coverage"
    elif fraction < 0.95:
        status = "partial_coverage"
    elif not np.any((frame.rate >= location.threshold) & circle):
        status = "no_precipitation_detected"
    if frame.quality is not None and (frame.quality_time is None or frame.quality_time <= now):
        target_quality = frame.quality[center]
        good_fraction = float(np.mean(frame.quality[circle] >= 0.8))
        quality = "radar_quality_good" if target_quality >= 0.8 and good_fraction >= 0.8 else "radar_quality_limited"
        if not np.isfinite(target_quality) or target_quality < 0.2:
            status = "insufficient_coverage"
        elif quality == "radar_quality_limited" and status in ("available", "no_precipitation_detected"):
            status = "partial_coverage"
    if age > 10:
        status = "stale_observations"
    return Coverage(status=status, valid_fraction=round(fraction, 4), target_valid=target_valid,
                    age_minutes=round(age, 2), quality=quality)


def render(frame: Frame, location: Location, as_of: datetime | None = None) -> dict:
    # Leaflet ImageOverlay needs a geographic raster; reproject, do not stretch the AEQD grid.
    bounds = transform_bounds(frame.crs, "EPSG:4326", *array_bounds(*frame.rate.shape, frame.transform))
    west, south, east, north = bounds
    if east < west:
        if location.lon < 0:
            west -= 360
        else:
            east += 360
    height, width = frame.rate.shape
    transform = rasterio.transform.from_bounds(west, south, east, north, width, height)
    bounds = [[south, west], [north, east]]

    def layer(field, unit, timestamp, source):
        output = np.full((height, width), np.nan, dtype="float32")
        reproject(field, output, src_transform=frame.transform, src_crs=frame.crs,
                  src_nodata=np.nan, dst_transform=transform, dst_crs="EPSG:4326",
                  dst_nodata=np.nan, resampling=Resampling.nearest)
        rgba = np.zeros((*output.shape, 4), dtype="uint8")
        if unit == "dBZ":
            palette = [(5, (105, 100, 183)), (10, (65, 140, 202)), (20, (46, 190, 150)),
                       (30, (140, 211, 75)), (40, (247, 206, 63)), (50, (242, 95, 48)),
                       (60, (214, 61, 153))]
        else:
            palette = [(0.1, (69, 185, 222)), (0.5, (60, 202, 148)), (2, (169, 220, 76)),
                       (5, (250, 207, 70)), (10, (249, 138, 57)), (25, (235, 68, 92)),
                       (50, (190, 80, 220))]
        for limit, color in palette:
            rgba[np.isfinite(output) & (output >= limit)] = (*color, 205)
        rgba[~np.isfinite(output)] = (111, 124, 143, 75)
        buffer = io.BytesIO()
        Image.fromarray(rgba).save(buffer, format="PNG")
        finite = np.isfinite(field)
        return {"time": timestamp.isoformat(), "source": source, "bounds": bounds,
                "image": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(),
                "unit": unit, "valid_fraction": float(finite.mean()),
                "max_value": float(np.max(field[finite])) if finite.any() else None,
                "echo_pixels": int(np.count_nonzero(finite & (field >= palette[0][0])))}

    rate = layer(frame.rate, "mm/h", frame.time, frame.source)
    rate["product"] = "PrecipRate"
    layers = {"rate": rate}
    if (frame.composite_reflectivity is not None
            and (as_of is None or frame.composite_reflectivity_time is None
                 or frame.composite_reflectivity_time <= as_of)):
        layers["reflectivity"] = layer(frame.composite_reflectivity, "dBZ",
                                       frame.composite_reflectivity_time or frame.time,
                                       frame.composite_reflectivity_source or frame.source)
        layers["reflectivity"]["product"] = "MergedReflectivityQCComposite"
    elif (frame.reflectivity is not None
          and (as_of is None or frame.reflectivity_time is None or frame.reflectivity_time <= as_of)):
        layers["reflectivity"] = layer(frame.reflectivity, "dBZ", frame.reflectivity_time or frame.time,
                                       frame.reflectivity_source or frame.source)
        layers["reflectivity"]["product"] = "ReflectivityAtLowestAltitude"
    # Keep the original rate overlay for older clients, but expose each physical field independently.
    return {"time": frame.time.isoformat(), "source": frame.source, "bounds": bounds,
            "image": rate["image"], "coverage": coverage(frame, location, frame.time).model_dump(),
            "layers": layers}
