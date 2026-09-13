from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ScheduleUnavailableError
from app.adapters.movieland import MovielandAdapter
from app.adapters.registry import registry
from app.data.cinemas import CINEMAS
from app.main import app

CINEMA = next(c for c in CINEMAS if c.chain == "movieland")
DAY = date(2026, 9, 13)


def event(**changes):
    return {
        "EventId": "123",
        "MovieId": 5022,
        "TheaterId": 1290,
        "Date": "2026-09-13T21:00:00",
        "ThreeD": False,
        "HebrewSubs": None,
        "BookingNativeUrl": "https://untrusted.example/",
        **changes,
    }


def payload(events):
    return [{"Name": "סרט לדוגמה", "MovieId": 5022, "Dates": events}]


def handler(request):
    assert request.method == "GET"
    assert request.url.host == "movieland.co.il"
    assert request.url.path == "/api/Events"
    assert dict(request.url.params) == {"TheatreId": "1290", "Date": "13/09/2026"}
    assert "authorization" not in request.headers
    return httpx.Response(
        200,
        json=payload(
            [
                event(),
                event(),
                event(
                    EventId="124",
                    Date="2026-09-13T18:00:00",
                    ThreeD=True,
                    IsVip=True,
                    HebrewSubs=True,
                ),
                event(TheaterId=1291),
                event(EventId="125", Date="2026-09-14T00:30:00"),
            ]
        ),
    )


@pytest.mark.asyncio
async def test_normalization_filters_and_deduplication():
    result = await MovielandAdapter(transport=httpx.MockTransport(handler)).get_screenings(
        cinema=CINEMA, date=DAY
    )
    assert [s.id for s in result] == ["movieland:1290:124", "movieland:1290:123"]
    assert result[0].format == "3D, VIP"
    assert result[0].subtitles == "he"
    s = result[1]
    assert s.starts_at.isoformat() == "2026-09-13T21:00:00+03:00"
    assert s.movie.title == "סרט לדוגמה"
    assert s.movie.id == "movieland:5022"
    assert s.language is s.subtitles is s.movie.poster_url is None
    assert s.format == "2D"
    assert s.booking_url == "https://movieland.co.il/order/?eventID=123&MovieId=5022&theaterId=1290"


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["2026-01-08T00:30:00", "2026-01-07T22:30:00Z"])
async def test_winter_timezone(when):
    adapter = MovielandAdapter(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=payload([event(Date=when, ThreeD=None)]))
        )
    )
    result = await adapter.get_screenings(cinema=CINEMA, date=date(2026, 1, 8))
    assert result[0].starts_at.isoformat() == "2026-01-08T00:30:00+02:00"
    assert result[0].format is None


@pytest.mark.asyncio
async def test_empty_and_unknown_cinema():
    adapter = MovielandAdapter(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    )
    assert await adapter.get_screenings(cinema=CINEMA, date=DAY) == []
    with pytest.raises(ScheduleUnavailableError, match="mapping"):
        await MovielandAdapter().get_screenings(
            cinema=CINEMA.model_copy(update={"id": "unknown"}), date=DAY
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["http", "timeout", "redirect", "json", "shape", "date", "mismatch", "id"]
)
async def test_failures(failure):
    calls = []

    def fail(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout")
        if failure == "http":
            return httpx.Response(503)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if failure == "json":
            return httpx.Response(200, text="invalid")
        body = {
            "shape": {},
            "date": payload([event(Date="invalid")]),
            "mismatch": payload([event(MovieId=999)]),
            "id": payload([event(EventId="../other")]),
        }[failure]
        return httpx.Response(200, json=body)

    with pytest.raises(ScheduleUnavailableError):
        await MovielandAdapter(transport=httpx.MockTransport(fail)).get_screenings(
            cinema=CINEMA, date=DAY
        )
    assert len(calls) == 1


def test_routes(monkeypatch):
    assert isinstance(registry.get("movieland"), MovielandAdapter)
    monkeypatch.setattr(
        registry,
        "_adapters",
        {"movieland": MovielandAdapter(transport=httpx.MockTransport(handler))},
    )
    with TestClient(app) as client:
        for query in ["", "&chain=movieland", "&cinema_id=movieland-karmiel"]:
            response = client.get("/api/screenings?date=2026-09-13" + query)
            assert response.status_code == 200
            assert len(response.json()) == 2


def test_endpoint_failure(monkeypatch):
    monkeypatch.setitem(
        registry._adapters,
        "movieland",
        MovielandAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(503))),
    )
    with TestClient(app) as client:
        r = client.get("/api/screenings?date=2026-09-13&chain=movieland")
    assert r.status_code == 502
    assert r.json() == {"detail": "Movieland schedule is unavailable"}
