from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.models.cinema import Cinema, Location
from app.models.screening import Screening


class SeatAvailability(BaseModel):
    total: int
    available: int
    occupied: int
    held: int
    unavailable: int
    unknown: int


class NearbyScreening(BaseModel):
    screening: Screening
    seat_status: Literal["available", "unsupported", "unavailable"]
    seat_availability: SeatAvailability | None = None


class NearbyCinema(BaseModel):
    cinema: Cinema
    distance_km: float = Field(ge=0)
    schedule_status: Literal["available", "unsupported", "unavailable"]
    screenings: list[NearbyScreening] = Field(default_factory=list)


class NearbySearchResponse(BaseModel):
    date: date
    origin: Location
    radius_km: float = Field(gt=0)
    cinemas: list[NearbyCinema]
