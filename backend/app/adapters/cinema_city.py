import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.base import ScheduleUnavailableError
from app.models.cinema import Cinema, Location
from app.models.screening import Movie, Screening
from app.models.seat import SeatLookup, SeatMap

BASE_URL = "https://www.cinema-city.co.il"
# TixTheatreId from the provider's theater directory, not its internal Id.
THEATER_IDS = {"cinema-city-glilot": 1170}


class _ProviderModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)


class _Movie(_ProviderModel):
    MovieId: str = Field(min_length=1)
    Name: str = Field(min_length=1)


class _Event(_ProviderModel):
    EventId: str = Field(min_length=1)
    TheaterId: int
    Date: str


class _EventGroup(_ProviderModel):
    Dates: list[_Event]


class CinemaCityAdapter:
    chain = "cinema_city"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def get_screenings(
        self, *, cinema: Cinema, date: date, location: Location | None = None
    ) -> list[Screening]:
        theater_id = THEATER_IDS.get(cinema.id)
        if cinema.chain != self.chain or theater_id is None:
            raise ScheduleUnavailableError("Cinema City theater mapping is missing")

        async with httpx.AsyncClient(
            base_url=BASE_URL, timeout=20.0, follow_redirects=False, transport=self._transport
        ) as client:
            try:
                movies = [
                    _Movie.model_validate(row) for row in await self._get(client, "/tickets/Movies")
                ]
                # Bound requests to the undocumented provider API.
                semaphore = asyncio.Semaphore(4)

                async def fetch(movie: _Movie) -> list[Screening]:
                    async with semaphore:
                        rows = await self._get(
                            client,
                            "/tickets/Events",
                            params={"MovieId": movie.MovieId, "Date": date.strftime("%d/%m/%Y")},
                        )
                    results = []
                    for row in rows:
                        for event in _EventGroup.model_validate(row).Dates:
                            if event.TheaterId != theater_id:
                                continue
                            starts_at = datetime.strptime(event.Date, "%d/%m/%Y %H:%M").replace(
                                tzinfo=ZoneInfo("Asia/Jerusalem")
                            )
                            if starts_at.date() != date:
                                continue
                            results.append(
                                Screening(
                                    id=f"cinema_city:{theater_id}:{event.EventId}",
                                    chain=self.chain,
                                    cinema_id=cinema.id,
                                    cinema_name=cinema.name,
                                    movie=Movie(
                                        id=f"cinema_city:{movie.MovieId}", title=movie.Name
                                    ),
                                    starts_at=starts_at,
                                    booking_url=str(
                                        httpx.URL(
                                            f"{BASE_URL}/order/",
                                            params={
                                                "eventID": event.EventId,
                                                "theaterId": str(theater_id),
                                            },
                                        )
                                    ),
                                )
                            )
                    return results

                movies = list({movie.MovieId: movie for movie in movies}.values())
                batches = await asyncio.gather(
                    *(fetch(movie) for movie in movies), return_exceptions=True
                )
                screenings = {}
                for batch in batches:
                    if isinstance(batch, BaseException):
                        raise batch
                    for screening in batch:
                        screenings[screening.id] = screening
                return sorted(screenings.values(), key=lambda item: item.starts_at)
            except (httpx.HTTPError, ValueError) as exc:
                raise ScheduleUnavailableError("Cinema City schedule is unavailable") from exc

    @staticmethod
    async def _get(client: httpx.AsyncClient, path: str, **kwargs) -> list[dict]:
        response = await client.get(path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ScheduleUnavailableError("Cinema City returned an invalid schedule response")
        return payload

    async def get_seats(self, *, screening: Screening | SeatLookup) -> SeatMap:
        from app.adapters.seat_lookup import validate_lookup

        _, event_id = validate_lookup(screening, expected_chain=self.chain)
        from app.adapters.presglobal_seats import get_seats

        return await get_seats(
            screening_id=screening.id, chain=self.chain, event_id=event_id,
            transport=self._transport,
        )
