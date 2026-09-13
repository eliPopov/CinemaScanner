from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ScheduleUnavailableError
from app.adapters.hot_cinema import HotCinemaAdapter
from app.adapters.hot_cinema_session import API_URL, HotCinemaSession, HotCinemaSessionError
from app.adapters.registry import registry
from app.data.cinemas import CINEMAS
from app.main import app

CINEMA = next(c for c in CINEMAS if c.chain == "hot_cinema")
DAY = date(2026, 9, 13)


def payload():
    event = {
        "EventId": "123",
        "TheaterId": 14,
        "Date": "2026-09-13T21:00:00",
        "DubbedLanguage": "עברית",
        "SubtitledLanguage": None,
        "Is3D": None,
    }
    return {
        "TheaterEvents": [
            {
                "MovieId": 1,
                "MovieName": "סרט",
                "Dates": [
                    event,
                    event,
                    {**event, "EventId": "124", "Date": "2026-09-13T18:00:00"},
                    {**event, "TheaterId": 99},
                    {**event, "Date": "2026-09-14T00:30:00"},
                ],
            }
        ]
    }


def schedule_handler(request):
    assert request.method == "GET"
    assert request.url.path == "/tickets/TheaterEvents2"
    assert dict(request.url.params) == {"theatreid": "14", "date": "13/09/2026"}
    assert "authorization" not in request.headers
    return httpx.Response(200, json=payload())


@pytest.mark.asyncio
async def test_schedule():
    result = await HotCinemaAdapter(transport=httpx.MockTransport(schedule_handler)).get_screenings(
        cinema=CINEMA, date=DAY
    )
    assert [r.id for r in result] == ["hot_cinema:14:124", "hot_cinema:14:123"]
    s = result[1]
    assert s.starts_at.isoformat() == "2026-09-13T21:00:00+03:00"
    assert s.movie.id == "hot_cinema:1"
    assert s.movie.title == "סרט"
    assert s.language == "עברית"
    assert s.format is s.subtitles is s.movie.poster_url is None
    assert s.booking_url == "https://www.hotcinema.co.il/order?theaterId=14&eventId=123"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "redirect", "timeout", "json", "schema"])
async def test_schedule_errors(failure):
    def handler(request):
        assert request.url.host == "www.hotcinema.co.il"
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout")
        if failure == "http":
            return httpx.Response(503)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})
        if failure == "json":
            return httpx.Response(200, text="not json")
        return httpx.Response(200, json={})

    with pytest.raises(ScheduleUnavailableError):
        await HotCinemaAdapter(transport=httpx.MockTransport(handler)).get_screenings(
            cinema=CINEMA, date=DAY
        )


def test_endpoint(monkeypatch):
    assert isinstance(registry.get("hot_cinema"), HotCinemaAdapter)
    monkeypatch.setattr(
        registry,
        "_adapters",
        {"hot_cinema": HotCinemaAdapter(transport=httpx.MockTransport(schedule_handler))},
    )
    with TestClient(app) as client:
        for query in ["", "&chain=hot_cinema", "&cinema_id=hot-cinema-petah-tikva"]:
            r = client.get("/api/screenings?date=2026-09-13" + query)
            assert r.status_code == 200
            assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_session_lazy_reuse_and_cleanup():
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url).startswith(API_URL + "/")
        if request.method == "POST":
            assert request.url.path.endswith("/sys/login")
            assert "authorization" not in request.headers
            assert request.content == b'{"siteId":1194,"saleChannelCode":"WEB","language":"he_IL"}'
            return httpx.Response(200, json={"token": "fake-test-token"})
        assert request.headers["Authorization"] == "Bearer fake-test-token"
        if "/code/" in request.url.path:
            assert request.url.path.endswith("/1194-123/min")
            return httpx.Response(200, json={"returnCode": 0, "list": [{"ei": 456}]})
        assert request.url.path.endswith("/456/seatsStatus")
        return httpx.Response(200, json={"returnCode": 0, "recordCount": 0})

    session = HotCinemaSession(site_id=1194, transport=httpx.MockTransport(handler))
    async with session:
        assert calls == []
        assert await session.get_event(123) == [{"ei": 456}]
        assert "fake-test-token" not in repr(session._token)
        assert await session.get_seat_status(456) == []
    assert len(calls) == 3
    assert session._token is session._client is None
    with pytest.raises(HotCinemaSessionError):
        await session.get_event(123)


@pytest.mark.asyncio
@pytest.mark.parametrize("always_expired", [True, False])
async def test_session_refresh_is_bounded(always_expired):
    logins = 0
    reads = 0

    def handler(request):
        nonlocal logins, reads
        if request.method == "POST":
            logins += 1
            return httpx.Response(200, json={"token": f"fake-{logins}"})
        reads += 1
        assert request.headers["Authorization"] == f"Bearer fake-{logins}"
        return (
            httpx.Response(401)
            if always_expired or reads == 1
            else httpx.Response(200, json={"returnCode": 0, "list": []})
        )

    session = HotCinemaSession(site_id=1194, transport=httpx.MockTransport(handler))
    async with session:
        if always_expired:
            with pytest.raises(HotCinemaSessionError):
                await session.get_event(123)
            assert session._token is None
        else:
            assert await session.get_event(123) == []
    assert logins == reads == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["login_redirect", "read_redirect", "bad_token", "bad_json", "provider_error"]
)
async def test_session_failures_and_cleanup(failure):
    def handler(request):
        assert request.url.host == "pub-api-use1.biggerpicture.ai"
        if request.method == "POST":
            if failure == "login_redirect":
                return httpx.Response(302, headers={"Location": "https://attacker.example/"})
            return httpx.Response(
                200, json={"token": "bad\r\ntoken" if failure == "bad_token" else "fake-token"}
            )
        if failure == "read_redirect":
            return httpx.Response(302, headers={"Location": "https://attacker.example/"})
        if failure == "bad_json":
            return httpx.Response(200, text="invalid")
        return httpx.Response(200, json={"returnCode": 1, "list": []})

    session = HotCinemaSession(site_id=1194, transport=httpx.MockTransport(handler))
    with pytest.raises(HotCinemaSessionError):
        async with session:
            await session.get_event(123)
    assert session._token is session._client is None


@pytest.mark.asyncio
async def test_session_rejects_path_injection():
    async with HotCinemaSession(site_id=1194) as session:
        with pytest.raises(ValueError):
            await session.get_event("../shoppingCart")
        with pytest.raises(ValueError):
            await session.get_seat_status("123?other=1")
