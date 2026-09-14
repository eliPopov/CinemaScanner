from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SeatLookup(BaseModel):
    id: str
    chain: str
    cinema_id: str


class Seat(BaseModel):
    id: str
    row: str
    number: str
    x: float | None = None
    y: float | None = None
    status: Literal["available", "occupied", "held", "unavailable", "unknown"]
    kind: str = "standard"
    section_id: str = "1"


class SeatMap(BaseModel):
    screening_id: str
    total: int
    available: int
    occupied: int
    seats: list[Seat]
    held: int = 0
    unavailable: int = 0
    unknown: int = 0
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def build_seat_map(screening_id: str, seats: list[Seat]) -> SeatMap:
    if not seats or len({seat.id for seat in seats}) != len(seats):
        raise ValueError("Empty or duplicate seat layout")
    counts = {
        status: sum(s.status == status for s in seats)
        for status in ("available", "occupied", "held", "unavailable", "unknown")
    }
    return SeatMap(screening_id=screening_id, total=len(seats), seats=seats, **counts)
