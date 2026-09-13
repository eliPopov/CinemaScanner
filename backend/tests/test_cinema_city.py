from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ScheduleUnavailableError
from app.adapters.cinema_city import CinemaCityAdapter
from app.adapters.registry import registry
from app.data.cinemas import CINEMAS
from app.main import app

CINEMA = next(cinema for cinema in CINEMAS if cinema.id == "cinema-city-glilot")
DAY = date(2026, 9, 8)


def event(event_id="123", theater_id=1170, when="08/09/2026 21:00"):
    return {"EventId": event_id, "TheaterId": theater_id, "Date": when, "Hour": "21:00"}


def schedule_handler(request):
    if request.url.path == "/tickets/Movies":
        return httpx.Response(200, json=[{"MovieId": 6123, "Name": "סרט לדוגמה"}])
    assert request.url.path == "/tickets/Events"
    assert dict(request.url.params) == {"MovieId": "6123", "Date": "08/09/2026"}
    return httpx.Response(
        200,
        json=[
            {
                "Name": "סרט לדוגמה",
                "Pic": "poster.jpg",
                "EventId": None,
                "Dates": [
                    event(),
                    event(),
                    event("456", when="08/09/2026 18:00"),
                    event("789", 1174),
                    event("999", when="09/09/2026 00:30"),
                ],
            }
        ],
    )


@pytest.mark.asyncio
async def test_normalization_filtering_sorting_and_deduplication():
    adapter = CinemaCityAdapter(transport=httpx.MockTransport(schedule_handler))
    results = await adapter.get_screenings(cinema=CINEMA, date=DAY)
    assert [item.id for item in results] == ["cinema_city:1170:456", "cinema_city:1170:123"]
    item = results[1]
    assert item.cinema_id == CINEMA.id
    assert item.cinema_name == CINEMA.name
    assert item.movie.id == "cinema_city:6123"
    assert item.movie.title == "סרט לדוגמה"
    assert item.starts_at.isoformat() == "2026-09-08T21:00:00+03:00"
    assert item.booking_url == "https://www.cinema-city.co.il/order/?eventID=123&theaterId=1170"
    assert item.language is item.subtitles is item.format is item.movie.poster_url is None


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/tickets/Movies", "/tickets/Events"])
@pytest.mark.parametrize("failure", ["http", "timeout", "json", "shape", "record"])
async def test_provider_failures_are_explicit(path, failure):
    def handler(request):
        if request.url.path != path:
            return schedule_handler(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "http":
            return httpx.Response(503)
        if failure == "json":
            return httpx.Response(200, text="<html>unavailable</html>")
        return httpx.Response(200, json={} if failure == "shape" else [{}])

    adapter = CinemaCityAdapter(transport=httpx.MockTransport(handler))
    with pytest.raises(ScheduleUnavailableError):
        await adapter.get_screenings(cinema=CINEMA, date=DAY)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_path", ["/tickets/Movies", "/tickets/Events"])
async def test_empty_schedule(empty_path):
    def handler(request):
        if request.url.path == empty_path:
            return httpx.Response(200, json=[])
        return schedule_handler(request)

    adapter = CinemaCityAdapter(transport=httpx.MockTransport(handler))
    assert await adapter.get_screenings(cinema=CINEMA, date=DAY) == []


@pytest.mark.asyncio
async def test_unknown_cinema_does_not_fetch():
    def handler(request):
        pytest.fail("Unmapped cinemas must not fetch schedules")

    adapter = CinemaCityAdapter(transport=httpx.MockTransport(handler))
    with pytest.raises(ScheduleUnavailableError):
        await adapter.get_screenings(cinema=CINEMA.model_copy(update={"id": "unknown"}), date=DAY)


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["08/01/2026 00:30", "invalid"])
async def test_winter_timezone_and_invalid_event_date(when):
    def handler(request):
        if request.url.path == "/tickets/Movies":
            return schedule_handler(request)
        assert request.url.params["Date"] == "08/01/2026"
        return httpx.Response(200, json=[{"Dates": [event(when=when)]}])

    adapter = CinemaCityAdapter(transport=httpx.MockTransport(handler))
    if when == "invalid":
        with pytest.raises(ScheduleUnavailableError):
            await adapter.get_screenings(cinema=CINEMA, date=date(2026, 1, 8))
    else:
        results = await adapter.get_screenings(cinema=CINEMA, date=date(2026, 1, 8))
        assert results[0].starts_at.isoformat() == "2026-01-08T00:30:00+02:00"


def test_registry_and_screenings_endpoint(monkeypatch):
    assert isinstance(registry.get("cinema_city"), CinemaCityAdapter)
    monkeypatch.delitem(registry._adapters, "yes_planet")
    monkeypatch.delitem(registry._adapters, "hot_cinema")
    monkeypatch.delitem(registry._adapters, "lev")
    monkeypatch.delitem(registry._adapters, "movieland")
    monkeypatch.setitem(
        registry._adapters,
        "cinema_city",
        CinemaCityAdapter(
            transport=httpx.MockTransport(schedule_handler),
        ),
    )
    with TestClient(app) as client:
        for query in ["", "&chain=cinema_city", "&cinema_id=cinema-city-glilot"]:
            response = client.get(f"/api/screenings?date=2026-09-08{query}")
            assert response.status_code == 200
            assert len(response.json()) == 2
            assert response.json()[0]["starts_at"] == "2026-09-08T18:00:00+03:00"
        assert client.get("/api/screenings?date=invalid").status_code == 422
        assert client.get("/api/screenings").status_code == 422
        for query in ["chain=yes_planet", "cinema_id=unknown"]:
            assert client.get(f"/api/screenings?date=2026-09-08&{query}").json() == []


def test_endpoint_returns_502_on_provider_failure(monkeypatch):
    monkeypatch.setitem(
        registry._adapters,
        "cinema_city",
        CinemaCityAdapter(
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        ),
    )
    with TestClient(app) as client:
        response = client.get("/api/screenings?date=2026-09-08")
    assert response.status_code == 502
    assert response.json() == {"detail": "Cinema City schedule is unavailable"}
