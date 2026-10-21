from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    radius_km: float = Field(default=50, ge=10, le=100, allow_inf_nan=False)
    threshold: float = Field(default=0.2, ge=0.1, le=10, allow_inf_nan=False)


class ReplayRequest(Location):
    start: AwareDatetime
    end: AwareDatetime
    sample: bool = False

    @model_validator(mode="after")
    def bounded_period(self):
        seconds = (self.end - self.start).total_seconds()
        if not 120 <= seconds <= 3600:
            raise ValueError("Replay must span 2 to 60 minutes")
        if self.end > datetime.now(self.end.tzinfo):
            raise ValueError("Replay cannot use future dates")
        return self


CoverageStatus = Literal[
    "available", "partial_coverage", "insufficient_coverage", "provider_unavailable",
    "stale_observations", "no_precipitation_detected",
]


class Coverage(BaseModel):
    status: CoverageStatus
    valid_fraction: float = 0
    target_valid: bool = False
    age_minutes: float | None = None
    quality: str = "unknown"
    reason: str | None = None


class Prediction(BaseModel):
    id: str
    level: Literal["informational", "preventive", "imminent"] = "informational"
    intensity: Literal["light", "moderate", "heavy"]
    peak_rate: float
    area_km2: float
    distance_km: float
    lat: float
    lon: float
    direction_deg: float | None = None
    speed_kmh: float | None = None
    arrival_minutes: list[float] | None = None
    arrival_status: Literal["estimated", "motion_uncertain", "stationary", "no_intersection",
                            "low_confidence", "beyond_horizon"] = "motion_uncertain"
    confidence: Literal["low", "medium", "high"] = "low"
    event: str = "observed"
    observation_time: datetime
    data_quality: str
    vector_end: list[float] | None = None
    polygon: list[list[float]] = Field(default_factory=list)

