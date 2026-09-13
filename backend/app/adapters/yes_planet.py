from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.adapters.base import ScheduleUnavailableError
from app.models.cinema import Cinema, Location
from app.models.screening import Movie, Screening
from app.models.seat import SeatMap

BASE_URL = "https://www.planetcinema.co.il"
API_PATH = "/il/data-api-service/v1/quickbook/10100"
# externalCode from Planet's public apiSitesList directory.
CINEMA_IDS = {"yes-planet-ayalon": "1025"}
# Exact booking hosts verified for the configured branches. Add hosts only after verification.
BOOKING_HOSTS = frozenset({"tickets5.planetcinema.co.il"})
ISRAEL = ZoneInfo("Asia/Jerusalem")
FORMATS = {"2d": "2D", "3d": "3D", "imax": "IMAX", "4dx": "4DX", "screenx": "ScreenX"}


class _ProviderModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)


class _Film(_ProviderModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    posterLink: HttpUrl | None = None
    videoLink: HttpUrl | None = None


class _Languages(BaseModel):
    original: list[str] = Field(default_factory=list)
    dubbed: list[str] = Field(default_factory=list)
    voiceover: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)


class _Event(_ProviderModel):
    id: str = Field(min_length=1)
    filmId: str = Field(min_length=1)
    cinemaId: str = Field(min_length=1)
    eventDateTime: datetime
    bookingLink: HttpUrl
    attributeIds: list[str] = Field(default_factory=list)
    languages: _Languages | None = None

    @field_validator("bookingLink")
    @classmethod
    def validate_booking_link(cls, url: HttpUrl) -> HttpUrl:
        if (
            url.scheme != "https"
            or url.host not in BOOKING_HOSTS
            or url.port != 443
            or url.username is not None
            or url.password is not None
        ):
            raise ValueError("Untrusted Planet booking URL")
        return url


class _Schedule(BaseModel):
    films: list[_Film]
    events: list[_Event]


class _Response(BaseModel):
    body: _Schedule


class YesPlanetAdapter:
    chain = "yes_planet"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def get_screenings(
        self, *, cinema: Cinema, date: date, location: Location | None = None
    ) -> list[Screening]:
        provider_id = CINEMA_IDS.get(cinema.id)
        if cinema.chain != self.chain or provider_id is None:
            raise ScheduleUnavailableError("Planet cinema mapping is missing")

        screenings: dict[str, Screening] = {}
        try:
            async with httpx.AsyncClient(
                base_url=BASE_URL, timeout=20.0, follow_redirects=False, transport=self._transport
            ) as client:
                # A business day can extend past midnight into the requested calendar day.
                days = [date - timedelta(days=1), date] if date > date.min else [date]
                for business_day in days:
                    response = await client.get(
                        f"{API_PATH}/film-events/in-cinema/{provider_id}/at-date/{business_day}"
                    )
                    response.raise_for_status()
                    schedule = _Response.model_validate(response.json()).body
                    films = {film.id: film for film in schedule.films}
                    for event in schedule.events:
                        if event.cinemaId != provider_id:
                            continue
                        starts_at = event.eventDateTime
                        if starts_at.tzinfo is None:
                            starts_at = starts_at.replace(tzinfo=ISRAEL)
                        else:
                            starts_at = starts_at.astimezone(ISRAEL)
                        if starts_at.date() != date:
                            continue
                        film = films.get(event.filmId)
                        if film is None:
                            raise ScheduleUnavailableError(
                                "Planet event references an unknown film"
                            )
                        languages = event.languages
                        spoken = (
                            languages.voiceover or languages.dubbed or languages.original
                            if languages
                            else []
                        )
                        formats = [
                            label for key, label in FORMATS.items() if key in event.attributeIds
                        ]
                        screening = Screening(
                            id=f"yes_planet:{provider_id}:{event.id}",
                            chain=self.chain,
                            cinema_id=cinema.id,
                            cinema_name=cinema.name,
                            movie=Movie(
                                id=f"yes_planet:{film.id}",
                                title=film.name,
                                poster_url=str(film.posterLink) if film.posterLink else None,
                                trailer_url=str(film.videoLink) if film.videoLink else None,
                            ),
                            starts_at=starts_at,
                            language=", ".join(spoken) or None,
                            subtitles=", ".join(languages.subtitles) or None if languages else None,
                            format=", ".join(formats) or None,
                            booking_url=str(event.bookingLink),
                        )
                        screenings[screening.id] = screening
        except (httpx.HTTPError, ValueError) as exc:
            raise ScheduleUnavailableError("Planet schedule is unavailable") from exc
        return sorted(screenings.values(), key=lambda screening: screening.starts_at)

    async def get_seats(self, *, screening: Screening) -> SeatMap:
        raise NotImplementedError("Planet seat lookup is not implemented")
