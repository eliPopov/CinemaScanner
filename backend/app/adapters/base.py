from datetime import date
from typing import Protocol

from app.models.cinema import Cinema, Location
from app.models.screening import Screening
from app.models.seat import SeatMap


class ScheduleUnavailableError(Exception):
    """The provider schedule could not be retrieved or validated."""


class CinemaAdapter(Protocol):
    chain: str

    async def get_screenings(
        self, *, cinema: Cinema, date: date, location: Location | None = None
    ) -> list[Screening]: ...

    async def get_seats(self, *, screening: Screening) -> SeatMap: ...
