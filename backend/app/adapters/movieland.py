from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.adapters.base import ScheduleUnavailableError
from app.models.cinema import Cinema, Location
from app.models.screening import Movie, Screening
from app.models.seat import SeatMap

BASE_URL = "https://movieland.co.il"
# TixTheatreId verified from the public branch selector.
THEATER_IDS = {"movieland-karmiel": 1290}
ISRAEL = ZoneInfo("Asia/Jerusalem")


class _ProviderModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)


class _Event(_ProviderModel):
    EventId: str = Field(pattern=r"^[0-9]+$")
    MovieId: str = Field(pattern=r"^[0-9]+$")
    TheaterId: int
    Date: datetime
    HebrewSubs: bool | None = None
    ThreeD: bool | None = None
    IsVip: bool | None = None


class _Movie(_ProviderModel):
    MovieId: str = Field(pattern=r"^[0-9]+$")
    Name: str = Field(min_length=1)
    Dates: list[_Event]


_SCHEDULE = TypeAdapter(list[_Movie])


class MovielandAdapter:
    chain = "movieland"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def get_screenings(
        self,
        *,
        cinema: Cinema,
        date: date,
        location: Location | None = None,
    ) -> list[Screening]:
        theater_id = THEATER_IDS.get(cinema.id)
        if cinema.chain != self.chain or theater_id is None:
            raise ScheduleUnavailableError("Movieland theater mapping is missing")
        try:
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=False, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{BASE_URL}/api/Events",
                    params={
                        "TheatreId": theater_id,
                        "Date": date.strftime("%d/%m/%Y"),
                    },
                )
                response.raise_for_status()
                movies = _SCHEDULE.validate_python(response.json())
            results = {}
            for movie in movies:
                for event in movie.Dates:
                    if event.TheaterId != theater_id:
                        continue
                    starts_at = event.Date
                    starts_at = (
                        starts_at.replace(tzinfo=ISRAEL)
                        if starts_at.tzinfo is None
                        else starts_at.astimezone(ISRAEL)
                    )
                    if starts_at.date() != date:
                        continue
                    if event.MovieId != movie.MovieId:
                        raise ValueError("Movieland movie/event mismatch")
                    formats = []
                    if event.ThreeD is not None:
                        formats.append("3D" if event.ThreeD else "2D")
                    if event.IsVip:
                        formats.append("VIP")
                    screening = Screening(
                        id=f"movieland:{theater_id}:{event.EventId}",
                        chain=self.chain,
                        cinema_id=cinema.id,
                        cinema_name=cinema.name,
                        movie=Movie(id=f"movieland:{movie.MovieId}", title=movie.Name),
                        starts_at=starts_at,
                        subtitles="he" if event.HebrewSubs else None,
                        format=", ".join(formats) or None,
                        booking_url=str(
                            httpx.URL(
                                f"{BASE_URL}/order/",
                                params={
                                    "eventID": event.EventId,
                                    "MovieId": event.MovieId,
                                    "theaterId": str(theater_id),
                                },
                            )
                        ),
                    )
                    results[screening.id] = screening
            return sorted(results.values(), key=lambda s: s.starts_at)
        except (httpx.HTTPError, ValueError) as exc:
            raise ScheduleUnavailableError("Movieland schedule is unavailable") from exc

    async def get_seats(self, *, screening: Screening) -> SeatMap:
        raise NotImplementedError("Movieland seat lookup is not implemented")
