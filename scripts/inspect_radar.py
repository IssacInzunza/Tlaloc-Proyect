"""Inspect real NOAA rates and reflectivity separately, without sending a watch point upstream."""
import argparse
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
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    if start.tzinfo is None or end.tzinfo is None or not 0 <= (end-start).total_seconds() <= 3600:
        parser.error("Use aware timestamps spanning at most one hour")
    location = Location(lat=args.lat, lon=args.lon)
    frames = MRMSProvider(ROOT / ".cache").frames(location, start, end)
    results = []
    for frame in frames:
        x, y = frame.xy()
        circle = x*x+y*y <= (location.radius_km*1000)**2
        info = {"time": frame.time.isoformat(), "source": frame.source}
        for name, field, threshold in (("rate", frame.rate, 0.1), ("reflectivity", frame.reflectivity, 5)):
            if field is None:
                info[name] = None
                continue
            finite = np.isfinite(field[circle])
            info[name] = {"valid_fraction": float(finite.mean()),
                          "max_value": float(np.nanmax(field[circle])) if finite.any() else None,
                          "echo_pixels": int(np.sum(field[circle] >= threshold))}
        results.append(info)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
