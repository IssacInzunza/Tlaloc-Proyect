"""Bounded, atomic tracking checkpoints; arrays never use pickle."""
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from zipfile import BadZipFile

import numpy as np
from pyproj import CRS
from rasterio import Affine

from .radar import Frame
from .tracking import Region


class TrackingStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def path(self, scope):
        return self.directory / (hashlib.sha256(scope.encode()).hexdigest() + ".npz")

    def save(self, scope, frame, regions):
        metadata = {"time": frame.time.isoformat(), "transform": list(frame.transform)[:6],
                    "crs": str(frame.crs), "source": frame.source, "regions": []}
        arrays = {"rate": frame.rate}
        for index, region in enumerate(regions):
            item = {key: value for key, value in asdict(region).items() if key != "mask"}
            metadata["regions"].append(item)
            arrays[f"mask_{index}"] = region.mask
        for name in ("reflectivity", "quality"):
            if getattr(frame, name) is not None:
                arrays[name] = getattr(frame, name)
        path = self.path(scope)
        try:
            with path.with_suffix(".tmp").open("wb") as stream:
                np.savez_compressed(stream, metadata=json.dumps(metadata), **arrays)
            path.with_suffix(".tmp").replace(path)
            for old in sorted(self.directory.glob("*.npz"), key=lambda p: p.stat().st_mtime, reverse=True)[8:]:
                old.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).warning("Tracking checkpoint could not be saved")

    def load(self, scope):
        path = self.path(scope)
        if not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                meta = json.loads(str(data["metadata"]))
                stamp = datetime.fromisoformat(meta["time"])
                # Never bridge an overnight gap or revive a stale trajectory after restarting.
                if not 0 <= (datetime.now(UTC)-stamp).total_seconds() <= 600:
                    return None
                frame = Frame(stamp, data["rate"], Affine(*meta["transform"]),
                              CRS.from_user_input(meta["crs"]), meta["source"],
                              reflectivity=data.get("reflectivity"),
                              quality=data.get("quality"))
                regions = [Region(mask=data[f"mask_{i}"], **item)
                           for i, item in enumerate(meta["regions"])]
                return frame, regions
        except (OSError, ValueError, KeyError, TypeError, BadZipFile):
            logging.getLogger(__name__).warning("Tracking checkpoint unavailable; rebuilding from observations")
            return None
