"""Capture a small, attributed real MRMS episode. Never generate simulated observations."""
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.models import Location
from app.providers import MRMSProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", required=True, help="ISO 8601 with UTC offset")
    parser.add_argument("--end", required=True, help="ISO 8601 with UTC offset")
    args = parser.parse_args()
    location = Location(lat=args.lat, lon=args.lon)
    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    if start.tzinfo is None or end.tzinfo is None or not 120 <= (end-start).total_seconds() <= 3600:
        parser.error("Use an aware 2–60 minute period")
    provider = MRMSProvider(ROOT / ".cache")
    frames = provider.frames(location, start, end)
    if len(frames) < 2:
        raise RuntimeError("No reproducible episode available")
    arrays = {f"rate_{i}": frame.rate for i, frame in enumerate(frames)}
    arrays.update({f"quality_{i}": frame.quality for i, frame in enumerate(frames) if frame.quality is not None})
    arrays.update({f"reflectivity_{i}": frame.reflectivity for i, frame in enumerate(frames) if frame.reflectivity is not None})
    arrays.update({f"composite_{i}": frame.composite_reflectivity for i, frame in enumerate(frames) if frame.composite_reflectivity is not None})
    path = ROOT / "samples" / "episode.npz"
    np.savez_compressed(path, **arrays)
    metadata = {"location": location.model_dump(), "unit": "mm/h", "synthetic": False,
                "attribution": "NOAA MRMS, processed and reprojected by Tláloc Project. No NOAA endorsement.",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "frames": [{"time": f.time.isoformat(), "source": f.source,
                            "reflectivity_source": f.reflectivity_source,
                            "quality_source": f.quality_source,
                            "reflectivity_time": f.reflectivity_time.isoformat() if f.reflectivity_time else None,
                            "quality_time": f.quality_time.isoformat() if f.quality_time else None,
                            "composite_reflectivity_source": f.composite_reflectivity_source,
                            "composite_reflectivity_time": f.composite_reflectivity_time.isoformat() if f.composite_reflectivity_time else None} for f in frames]}
    (ROOT / "samples" / "episode.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"frames": len(frames), "bytes": path.stat().st_size, "location": location.model_dump()}))


if __name__ == "__main__":
    main()
