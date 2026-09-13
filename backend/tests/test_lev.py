from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ScheduleUnavailableError
from app.adapters.lev import EMPTY_MESSAGE, LOCATIONS, SCHEDULE_PATH, LevAdapter
from app.adapters.registry import registry
from app.data.cinemas import CINEMAS
from app.main import app

CINEMA = next(c for c in CINEMAS if c.chain == "lev")
DAY = date(2026, 9, 13)


def row(code="123", hour="21:00"):
    return f'''<li><a class="topmenua" href="https://www.lev.co.il/order/?pcode={code}&amp;loc=6"
        data-pcode="{code}" data-siteid="6">סרט &amp; דוגמה <span>{hour}</span></a>
        <a class="smovielink" href="https://www.lev.co.il/movies/example/">תקציר</a></li>'''


def handler(request):
    assert request.method == "GET"
    assert request.url.host == "www.lev.co.il"
    assert request.url.path == SCHEDULE_PATH
    assert dict(request.url.params) == {
        "clang": "he",
        "action": "movie_on_location_new",
        "loc": LOCATIONS[CINEMA.id],
        "date": "2026-09-13",
    }
    return httpx.Response(
        200, text=row() + row() + row("124", "18:00") + "<!--" + row("999") + "-->"
    )


@pytest.mark.asyncio
async def test_normalization_and_commented_duplicates():
    result = await LevAdapter(transport=httpx.MockTransport(handler)).get_screenings(
        cinema=CINEMA, date=DAY
    )
    assert [s.id for s in result] == ["lev:6:124", "lev:6:123"]
    s = result[1]
    assert s.movie.title == "סרט & דוגמה"
    assert s.movie.id == "lev:/movies/example"
    assert s.cinema_id == CINEMA.id
    assert s.starts_at.isoformat() == "2026-09-13T21:00:00+03:00"
    assert s.language is s.subtitles is s.format is s.movie.poster_url is None
    assert s.booking_url == "https://www.lev.co.il/order/?pcode=123&loc=6"


@pytest.mark.asyncio
async def test_winter_midnight():
    adapter = LevAdapter(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=row(hour="00:30")))
    )
    result = await adapter.get_screenings(cinema=CINEMA, date=date(2026, 1, 8))
    assert result[0].starts_at.isoformat() == "2026-01-08T00:30:00+02:00"


@pytest.mark.asyncio
async def test_explicit_no_schedule_message():
    adapter = LevAdapter(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text=f" <li>{EMPTY_MESSAGE}</li> ")
        )
    )
    assert await adapter.get_screenings(cinema=CINEMA, date=DAY) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "html",
    [
        "",
        "0",
        "<html>Maintenance</html>",
        "<li>Unexpected message</li>",
        row(hour="25:00"),
        row().replace("<span>21:00</span>", ""),
        row().replace('data-pcode="123"', 'data-pcode=""'),
        row().replace("pcode=123", "pcode=456"),
        row().replace("https://www.lev.co.il/order/", "https://attacker.example/order/"),
        row().replace("https://www.lev.co.il", "http://www.lev.co.il"),
        row().replace("/movies/example/", "/unrelated/"),
        row() + "<li>Malformed additional event</li>",
    ],
)
async def test_invalid_html_and_urls_fail_explicitly(html):
    with pytest.raises(ScheduleUnavailableError):
        await LevAdapter(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html))
        ).get_screenings(cinema=CINEMA, date=DAY)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "timeout", "redirect"])
async def test_transport_failures(failure):
    calls = []

    def fail(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout")
        return (
            httpx.Response(503)
            if failure == "http"
            else httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        )

    with pytest.raises(ScheduleUnavailableError):
        await LevAdapter(transport=httpx.MockTransport(fail)).get_screenings(
            cinema=CINEMA, date=DAY
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_unknown_cinema_does_not_fetch():
    with pytest.raises(ScheduleUnavailableError, match="mapping"):
        await LevAdapter().get_screenings(
            cinema=CINEMA.model_copy(update={"id": "unknown"}), date=DAY
        )


def test_registered_adapter_and_routes(monkeypatch):
    assert isinstance(registry.get("lev"), LevAdapter)
    monkeypatch.setattr(
        registry, "_adapters", {"lev": LevAdapter(transport=httpx.MockTransport(handler))}
    )
    with TestClient(app) as client:
        for query in ["", "&chain=lev", "&cinema_id=lev-tel-aviv"]:
            response = client.get("/api/screenings?date=2026-09-13" + query)
            assert response.status_code == 200
            assert len(response.json()) == 2
        assert client.get("/api/screenings?date=2026-09-13&cinema_id=unknown").json() == []


def test_endpoint_failure(monkeypatch):
    monkeypatch.setitem(
        registry._adapters,
        "lev",
        LevAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(503))),
    )
    with TestClient(app) as client:
        response = client.get("/api/screenings?date=2026-09-13&chain=lev")
    assert response.status_code == 502
    assert response.json() == {"detail": "Lev schedule is unavailable"}
