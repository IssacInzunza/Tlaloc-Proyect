"""Connected-component tracking with translation priors and conservative association."""
import hashlib
from dataclasses import dataclass

import cv2
import numpy as np

from .radar import Frame


@dataclass
class Region:
    id: str
    mask: np.ndarray
    x: float
    y: float
    area: float
    peak: float
    mean: float
    vx: float | None = None
    vy: float | None = None
    confidence: str = "low"
    event: str = "observed"
    age: int = 1
    reflectivity: float | None = None


def segment(frame: Frame, threshold: float = 0.2) -> list[Region]:
    wet = (np.isfinite(frame.rate) & (frame.rate >= threshold)).astype("uint8")
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(wet, connectivity=8)
    result = []
    # Remove isolated sub-2 km² speckles; keep all larger weak precipitation echoes.
    for label in range(1, count):
        area = float(stats[label, cv2.CC_STAT_AREA]) * (frame.spacing / 1000)**2
        if area < 2:
            continue
        mask = labels == label
        col, row = centroids[label]
        x = frame.transform.c + (col + 0.5) * frame.spacing
        y = frame.transform.f - (row + 0.5) * frame.spacing
        identity = hashlib.sha1(f"{frame.time.isoformat()}:{label}:{x:.0f}:{y:.0f}".encode()).hexdigest()[:12]
        refl = None
        if (frame.reflectivity is not None
                and (frame.reflectivity_time is None or frame.reflectivity_time <= frame.time)
                and np.any(np.isfinite(frame.reflectivity[mask]))):
            refl = float(np.nanmax(frame.reflectivity[mask]))
        result.append(Region(identity, mask, x, y, area, float(np.nanmax(frame.rate[mask])),
                             float(np.nanmean(frame.rate[mask])), reflectivity=refl))
    # Bound work for noisy fields. Largest regions have priority; report this limitation in docs.
    return sorted(result, key=lambda r: r.area, reverse=True)[:100]


def associate(previous: Frame, current: Frame, old: list[Region], new: list[Region]):
    dt = (current.time - previous.time).total_seconds()
    if (not 30 <= dt <= 600 or previous.rate.shape != current.rate.shape
            or previous.transform != current.transform or previous.crs != current.crs):
        for region in new:
            region.event = "gap_uncertain"
        return new
    if not old or not new:
        for region in new:
            boundary = _boundary(region.mask)
            known = np.isfinite(previous.rate[region.mask]).mean() > 0.95
            region.event = "new_echo" if known and not boundary else "coverage_uncertain"
        return new
    common = np.isfinite(previous.rate) & np.isfinite(current.rate)
    if common.mean() < 0.6:
        for region in new:
            region.event = "coverage_uncertain"
        return new
    a = np.where(common, np.log1p(np.nan_to_num(previous.rate)), 0).astype("float32")
    b = np.where(common, np.log1p(np.nan_to_num(current.rate)), 0).astype("float32")
    shift, response = cv2.phaseCorrelate(a, b)
    dx, dy = shift[0]*current.spacing, -shift[1]*current.spacing
    if not np.isfinite([dx, dy, response]).all() or np.hypot(dx, dy)/dt > 55 or response < 0.08:
        # Failed registration is absence of evidence, not evidence of stationarity.
        for region in new:
            region.event = "motion_uncertain"
        return new
    max_distance = 55 * dt + current.spacing*2
    # One warp per prior component, rather than one full-raster warp per pair.
    matrix = np.array([[1, 0, dx/current.spacing], [0, 1, -dy/current.spacing]], dtype="float32")
    moved_masks = [cv2.warpAffine(prior.mask.astype("uint8"), matrix,
                   (current.rate.shape[1], current.rate.shape[0]), flags=cv2.INTER_NEAREST) > 0
                   for prior in old]
    moved_sizes = [np.count_nonzero(mask) for mask in moved_masks]
    new_sizes = [np.count_nonzero(region.mask) for region in new]
    candidates = {}
    reverse = {}
    for i, region in enumerate(new):
        candidates[i] = []
        for j, prior in enumerate(old):
            distance = np.hypot(region.x - prior.x, region.y - prior.y)
            if distance > max_distance:
                continue
            moved = moved_masks[j]
            overlap = np.count_nonzero(moved & region.mask) / max(1, min(moved_sizes[j], new_sizes[i]))
            residual = np.hypot(region.x-prior.x-dx, region.y-prior.y-dy)
            if overlap >= 0.15 or residual <= 3500:
                candidates[i].append((j, overlap, residual))
                reverse.setdefault(j, []).append(i)
    for i, region in enumerate(new):
        choices = candidates[i]
        if not choices:
            # A new echo can only be asserted if previous coverage covered its entire footprint.
            known = np.isfinite(previous.rate[region.mask]).mean() > 0.95
            boundary = _boundary(region.mask)
            region.event = "new_echo" if known and not boundary else "coverage_uncertain"
            continue
        if len(choices) != 1:
            region.event = "merge_uncertain"
            continue
        j, overlap, residual = choices[0]
        if len(reverse[j]) > 1:
            region.event = "split_uncertain"
            continue
        prior = old[j]
        region.id, region.age = prior.id, prior.age+1
        if (_boundary(prior.mask) or _boundary(region.mask)
                or np.isfinite(previous.rate[region.mask]).mean() < 0.95
                or np.isfinite(current.rate[moved_masks[j]]).mean() < 0.95):
            region.event = "coverage_uncertain"
            continue
        region.vx, region.vy = (region.x-prior.x)/dt, (region.y-prior.y)/dt
        ratio = region.area/prior.area
        if (not 0.5 <= ratio <= 2 or np.hypot(region.vx, region.vy) > 55
                or overlap < 0.35 or residual > max(2*current.spacing, 0.25*np.hypot(dx, dy))):
            region.vx = region.vy = None
            region.event = "shape_uncertain"
            continue
        region.confidence = "medium" if overlap >= 0.35 else "low"
        if prior.vx is not None and overlap >= 0.65:
            acceleration = np.hypot(region.vx-prior.vx, region.vy-prior.vy)
            if acceleration < 5 and region.age >= 3:
                region.confidence = "high"
        if ratio > 1.25:
            region.event = "growing"
        elif ratio < 0.75:
            region.event = "weakening"
        if region.mean > prior.mean * 1.3 and region.mean-prior.mean > 0.5:
            region.event = "intensifying"
        elif region.mean < prior.mean * 0.7:
            region.event = "weakening"
        if (region.reflectivity is not None and prior.reflectivity is not None
                and region.reflectivity-prior.reflectivity >= 5):
            region.event = "reflectivity_increasing"
        if region.event != "observed" and region.confidence == "high":
            region.confidence = "medium"
    return new


def _boundary(mask):
    return mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any()


def track(frames: list[Frame], threshold=0.2):
    old = []
    previous = None
    for frame in frames:
        new = segment(frame, threshold)
        if previous is not None:
            new = associate(previous, frame, old, new)
        old, previous = new, frame
    return old
