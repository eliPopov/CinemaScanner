from datetime import date, datetime
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Comment

from app.adapters.base import ScheduleUnavailableError
from app.models.cinema import Cinema, Location
from app.models.screening import Movie, Screening
from app.models.seat import SeatLookup, SeatMap

BASE_URL = "https://www.lev.co.il"
SCHEDULE_PATH = "/wp-content/themes/lev/ajax_data.php"
# Values from the website's locationfilter1 select, not the legacy numeric location IDs.
LOCATIONS = {"lev-tel-aviv": "לב תל אביב"}
EMPTY_MESSAGE = 'רשימת הסרטים לסופ"ש מתעדכנת עד ליום שלישי אחה"צ של אותו שבוע'
ISRAEL = ZoneInfo("Asia/Jerusalem")


def _lev_url(value: str) -> httpx.URL:
    url = httpx.URL(value)
    if (
        url.scheme != "https"
        or url.host != "www.lev.co.il"
        or url.port not in (None, 443)
        or url.userinfo
        or url.fragment
    ):
        raise ValueError("Unexpected Lev URL")
    return url


def _parse(html: str, cinema: Cinema, day: date) -> list[Screening]:
    soup = BeautifulSoup(html, "html.parser")
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    rows = soup.find_all("li")
    if (
        len(rows) == 1
        and not rows[0].find("a")
        and " ".join(soup.stripped_strings) == EMPTY_MESSAGE
    ):
        return []
    if not rows or soup.find(["html", "script", "form"]):
        raise ValueError("Unrecognized Lev schedule response")
    results = {}
    for row in rows:
        links = row.select("a.topmenua")
        movie_links = row.select("a.smovielink")
        if len(links) != 1 or len(movie_links) != 1:
            raise ValueError("Incomplete Lev screening")
        link = links[0]
        code, site = link.get("data-pcode", ""), link.get("data-siteid", "")
        if not code.isascii() or not code.isdecimal() or not site.isascii() or not site.isdecimal():
            raise ValueError("Invalid Lev booking identifiers")
        booking = _lev_url(link.get("href", ""))
        if booking.path != "/order/" or sorted(booking.params.multi_items()) != sorted(
            [
                ("pcode", code),
                ("loc", site),
            ]
        ):
            raise ValueError("Inconsistent Lev booking link")
        times = link.find_all("span")
        if len(times) != 1:
            raise ValueError("Missing Lev screening time")
        time_text = times[0].get_text(strip=True)
        starts_at = datetime.strptime(f"{day.isoformat()} {time_text}", "%Y-%m-%d %H:%M").replace(
            tzinfo=ISRAEL
        )
        times[0].extract()
        title = " ".join(link.stripped_strings)
        movie_url = _lev_url(movie_links[0].get("href", ""))
        if (
            not title
            or not movie_url.path.startswith("/movies/")
            or not movie_url.path.removeprefix("/movies/").strip("/")
        ):
            raise ValueError("Missing Lev movie identity")
        screening = Screening(
            id=f"lev:{site}:{code}",
            chain="lev",
            cinema_id=cinema.id,
            cinema_name=cinema.name,
            movie=Movie(id=f"lev:{unquote(movie_url.path).rstrip('/')}", title=title),
            starts_at=starts_at,
            booking_url=str(httpx.URL(f"{BASE_URL}/order/", params={"pcode": code, "loc": site})),
        )
        results[screening.id] = screening
    return sorted(results.values(), key=lambda s: s.starts_at)


class LevAdapter:
    chain = "lev"

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def get_screenings(
        self,
        *,
        cinema: Cinema,
        date: date,
        location: Location | None = None,
    ) -> list[Screening]:
        provider_location = LOCATIONS.get(cinema.id)
        if cinema.chain != self.chain or provider_location is None:
            raise ScheduleUnavailableError("Lev cinema mapping is missing")
        try:
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=False, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{BASE_URL}{SCHEDULE_PATH}",
                    params={
                        "clang": "he",
                        "action": "movie_on_location_new",
                        "loc": provider_location,
                        "date": date.isoformat(),
                    },
                )
                response.raise_for_status()
                return _parse(response.text, cinema, date)
        except (httpx.HTTPError, ValueError) as exc:
            raise ScheduleUnavailableError("Lev schedule is unavailable") from exc

    async def get_seats(self, *, screening: Screening | SeatLookup) -> SeatMap:
        from app.adapters.seat_lookup import validate_lookup

        _, event_id = validate_lookup(screening, expected_chain=self.chain)
        from app.adapters.presglobal_seats import get_seats

        return await get_seats(
            screening_id=screening.id, chain=self.chain, event_id=event_id,
            transport=self._transport,
        )
