from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ScheduleUnavailableError
from app.adapters.cinema_city import CinemaCityAdapter
from app.adapters.registry import registry
from app.adapters.yes_planet import API_PATH, YesPlanetAdapter
from app.data.cinemas import CINEMAS
from app.main import app

CINEMA = next(c for c in CINEMAS if c.id == "yes-planet-ayalon")
DAY = date(2026, 9, 13)
FILM = {"id": "8023s2r", "name": "סרט לדוגמה", "posterLink": "https://example.com/poster.jpg"}


def event(event_id="324292", when="2026-09-13T12:00:00", **changes):
    return {
        "id": event_id,
        "filmId": FILM["id"],
        "cinemaId": "1025",
        "eventDateTime": when,
        "businessDay": "2026-09-13",
        "bookingLink": f"https://tickets5.planetcinema.co.il/api/order/{event_id}?lang=he",
        "attributeIds": ["2d", "dubbed", "dubbed-lang-he", "original-lang-en"],
        "languages": {"original": ["en"], "dubbed": ["he"], "subtitles": ["he", "en"]},
        **changes,
    }


def payload(events):
    return {"body": {"films": [FILM], "events": events}}


def handler(request):
    assert request.method == "GET"
    assert request.url.host == "www.planetcinema.co.il"
    prefix = f"{API_PATH}/film-events/in-cinema/1025/at-date/"
    if request.url.path == prefix + "2026-09-12":
        return httpx.Response(
            200,
            json=payload(
                [
                    event("early", "2026-09-13T00:30:00", businessDay="2026-09-12"),
                    event("yesterday", "2026-09-12T21:00:00"),
                ]
            ),
        )
    assert request.url.path == prefix + "2026-09-13"
    return httpx.Response(
        200,
        json=payload(
            [
                event(),
                event(),
                event("other", cinemaId="9999"),
                event("tomorrow", "2026-09-14T00:30:00"),
            ]
        ),
    )


@pytest.mark.asyncio
async def test_normalization_calendar_filtering_and_deduplication():
    results = await YesPlanetAdapter(transport=httpx.MockTransport(handler)).get_screenings(
        cinema=CINEMA,
        date=DAY,
    )
    assert [s.id for s in results] == ["yes_planet:1025:early", "yes_planet:1025:324292"]
    s = results[1]
    assert s.cinema_id == CINEMA.id
    assert s.cinema_name == CINEMA.name
    assert s.chain == "yes_planet"
    assert s.starts_at.isoformat() == "2026-09-13T12:00:00+03:00"
    assert s.movie.title == FILM["name"]
    assert s.movie.id == "yes_planet:8023s2r"
    assert s.movie.poster_url == FILM["posterLink"]
    assert s.movie.rating is s.movie.original_title is s.movie.trailer_url is None
    assert (s.language, s.subtitles, s.format) == ("he", "he, en", "2D")
    assert s.booking_url == event()["bookingLink"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "when,expected",
    [
        ("2026-01-08T21:00:00", "2026-01-08T21:00:00+02:00"),
        ("2026-01-08T19:00:00Z", "2026-01-08T21:00:00+02:00"),
    ],
)
async def test_timezone_and_unknown_metadata(when, expected):
    adapter = YesPlanetAdapter(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json=payload([event(when=when, languages=None, attributeIds=["unknown"])]),
            )
        )
    )
    results = await adapter.get_screenings(cinema=CINEMA, date=date(2026, 1, 8))
    assert results[0].starts_at.isoformat() == expected
    assert results[0].language is results[0].subtitles is results[0].format is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "timeout", "json", "shape", "date", "film", "url"])
async def test_failures_do_not_return_partial_results(failure):
    def fail(request):
        if request.url.path.endswith("2026-09-12"):
            return handler(request)
        if failure == "http":
            return httpx.Response(503)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "json":
            return httpx.Response(200, text="<html>error</html>")
        body = {
            "shape": {},
            "date": payload([event(when="bad")]),
            "film": payload([event(filmId="missing")]),
            "url": payload([event(bookingLink="javascript:invalid")]),
        }[failure]
        return httpx.Response(200, json=body)

    with pytest.raises(ScheduleUnavailableError):
        await YesPlanetAdapter(transport=httpx.MockTransport(fail)).get_screenings(
            cinema=CINEMA, date=DAY
        )


@pytest.mark.asyncio
async def test_empty_schedule():
    adapter = YesPlanetAdapter(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={"body": {"films": [], "events": []}},
            )
        )
    )
    assert await adapter.get_screenings(cinema=CINEMA, date=DAY) == []


@pytest.mark.asyncio
async def test_unmapped_cinema():
    with pytest.raises(ScheduleUnavailableError, match="mapping"):
        await YesPlanetAdapter().get_screenings(
            cinema=CINEMA.model_copy(update={"id": "unknown"}),
            date=DAY,
        )


def test_registered_adapter_and_endpoint_filters(monkeypatch):
    assert isinstance(registry.get("yes_planet"), YesPlanetAdapter)
    monkeypatch.delitem(registry._adapters, "hot_cinema")
    monkeypatch.delitem(registry._adapters, "lev")
    monkeypatch.delitem(registry._adapters, "movieland")
    monkeypatch.setitem(
        registry._adapters,
        "yes_planet",
        YesPlanetAdapter(
            transport=httpx.MockTransport(handler),
        ),
    )
    # Both registered providers are mocked even for the unfiltered endpoint.
    monkeypatch.setitem(
        registry._adapters,
        "cinema_city",
        CinemaCityAdapter(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
        ),
    )
    with TestClient(app) as client:
        for query in ["", "&chain=yes_planet", "&cinema_id=yes-planet-ayalon"]:
            response = client.get(f"/api/screenings?date=2026-09-13{query}")
            assert response.status_code == 200
            assert [s["id"] for s in response.json()] == [
                "yes_planet:1025:early",
                "yes_planet:1025:324292",
            ]


def test_endpoint_provider_failure(monkeypatch):
    monkeypatch.setitem(
        registry._adapters,
        "yes_planet",
        YesPlanetAdapter(
            transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        ),
    )
    with TestClient(app) as client:
        r = client.get("/api/screenings?date=2026-09-13&chain=yes_planet")
    assert r.status_code == 502
    assert r.json() == {"detail": "Planet schedule is unavailable"}
