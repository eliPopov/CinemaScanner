from pydantic import BaseModel


class Seat(BaseModel):
    id: str
    row: str
    number: str
    x: float | None = None
    y: float | None = None
    status: str
    kind: str = "standard"


class SeatMap(BaseModel):
    screening_id: str
    total: int
    available: int
    occupied: int
    seats: list[Seat]

