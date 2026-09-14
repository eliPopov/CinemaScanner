from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.base import ScheduleUnavailableError
from app.adapters.hot_cinema_session import HotCinemaSession
from app.models.cinema import Cinema, Location
from app.models.screening import Movie, Screening
from app.models.seat import SeatLookup, SeatMap

BASE_URL = "https://www.hotcinema.co.il"
# Public theater ID and Bigger Picture site ID verified from the theater/booking pages.
CINEMA_IDS = {"hot-cinema-petah-tikva": (14, 1194)}
ISRAEL = ZoneInfo("Asia/Jerusalem")


class _ProviderModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)


class _Event(_ProviderModel):
    EventId: str = Field(pattern=r"^[0-9]+$")
    TheaterId: int
    Date: datetime
    DubbedLanguage: str | None = None
    SubtitledLanguage: str | None = None
    Is3D: bool | None = None
    IsAtmos2D: bool | None = None
    IsAtmos3D: bool | None = None
    IsAtmos: bool | None = None
    IsVIP: bool | None = None


class _Movie(_ProviderModel):
    MovieId: str = Field(min_length=1)
    MovieName: str = Field(min_length=1)
    Dates: list[_Event]


class _Response(BaseModel):
    TheaterEvents: list[_Movie]


class HotCinemaAdapter:
    chain = "hot_cinema"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    def _cinema_ids(self, cinema: Cinema) -> tuple[int, int]:
        ids = CINEMA_IDS.get(cinema.id)
        if cinema.chain != self.chain or ids is None:
            raise ScheduleUnavailableError("Hot Cinema theater mapping is missing")
        return ids

    def open_session(self, *, cinema: Cinema) -> HotCinemaSession:
        """Create an isolated, lazy session for subsequent read-only event/seat requests."""
        _, site_id = self._cinema_ids(cinema)
        return HotCinemaSession(site_id=site_id, transport=self._transport)

    async def get_screenings(
        self,
        *,
        cinema: Cinema,
        date: date,
        location: Location | None = None,
    ) -> list[Screening]:
        theater_id, _ = self._cinema_ids(cinema)
        try:
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=False, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{BASE_URL}/tickets/TheaterEvents2",
                    params={
                        "theatreid": theater_id,
                        "date": date.strftime("%d/%m/%Y"),
                    },
                )
                response.raise_for_status()
                payload = _Response.model_validate(response.json())
            results = {}
            for movie in payload.TheaterEvents:
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
                    formats = []
                    if event.Is3D or event.IsAtmos3D:
                        formats.append("3D")
                    elif event.Is3D is False or event.IsAtmos2D:
                        formats.append("2D")
                    if event.IsAtmos or event.IsAtmos2D or event.IsAtmos3D:
                        formats.append("Atmos")
                    if event.IsVIP:
                        formats.append("PREMIUM")
                    screening = Screening(
                        id=f"hot_cinema:{theater_id}:{event.EventId}",
                        chain=self.chain,
                        cinema_id=cinema.id,
                        cinema_name=cinema.name,
                        movie=Movie(id=f"hot_cinema:{movie.MovieId}", title=movie.MovieName),
                        starts_at=starts_at,
                        language=event.DubbedLanguage or None,
                        subtitles=event.SubtitledLanguage or None,
                        format=", ".join(formats) or None,
                        booking_url=str(
                            httpx.URL(
                                f"{BASE_URL}/order",
                                params={
                                    "theaterId": str(theater_id),
                                    "eventId": event.EventId,
                                },
                            )
                        ),
                    )
                    results[screening.id] = screening
            return sorted(results.values(), key=lambda s: s.starts_at)
        except (httpx.HTTPError, ValueError) as exc:
            raise ScheduleUnavailableError("Hot Cinema schedule is unavailable") from exc

    async def get_seats(self, *, screening: Screening | SeatLookup) -> SeatMap:
        from app.adapters.seat_lookup import validate_lookup

        _, event_id = validate_lookup(screening, expected_chain=self.chain)
        from app.adapters.bigger_picture_seats import get_seats

        return await get_seats(
            screening_id=screening.id, site_id=1194, event_id=event_id,
            transport=self._transport,
        )
