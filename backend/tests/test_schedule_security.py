from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ScheduleUnavailableError
from app.adapters.cinema_city import CinemaCityAdapter
from app.adapters.registry import registry
from app.adapters.yes_planet import YesPlanetAdapter
from app.data.cinemas import CINEMAS
from app.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["movies", "events", "planet"])
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_redirects_are_rejected_without_following(target, status):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host in {"www.cinema-city.co.il", "www.planetcinema.co.il"}
        if target == "events" and request.url.path == "/tickets/Movies":
            return httpx.Response(200, json=[{"MovieId": 1, "Name": "Example"}])
        return httpx.Response(status, headers={"Location": "http://127.0.0.1:9000/private"})

    adapter_type = YesPlanetAdapter if target == "planet" else CinemaCityAdapter
    adapter = adapter_type(transport=httpx.MockTransport(handler))
    cinema = next(c for c in CINEMAS if c.chain == adapter.chain)
    with pytest.raises(ScheduleUnavailableError):
        await adapter.get_screenings(cinema=cinema, date=date(2026, 9, 13))
    assert len(calls) == (2 if target == "events" else 1)


@pytest.mark.parametrize(
    "url",
    [
        "http://tickets5.planetcinema.co.il/api/order/1",
        "https://unrelated.example/checkout",
        "https://tickets5.planetcinema.co.il.attacker.example/checkout",
        "https://attacker-tickets5.planetcinema.co.il/checkout",
        "https://tickets5.planetcinema.co.il@attacker.example/checkout",
        "https://user:password@tickets5.planetcinema.co.il/api/order/1",
        "https://tickets5.planetcinema.co.il:8443/api/order/1",
        "https://127.0.0.1/api/order/1",
    ],
)
def test_untrusted_booking_urls_return_502(monkeypatch, url):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "body": {
                    "films": [{"id": "f", "name": "Example"}],
                    "events": [
                        {
                            "id": "e",
                            "filmId": "f",
                            "cinemaId": "1025",
                            "eventDateTime": "2026-09-13T12:00:00",
                            "bookingLink": url,
                        }
                    ],
                }
            },
        )

    monkeypatch.setitem(
        registry._adapters,
        "yes_planet",
        YesPlanetAdapter(
            transport=httpx.MockTransport(handler),
        ),
    )
    with TestClient(app) as client:
        response = client.get("/api/screenings?date=2026-09-13&chain=yes_planet")
    assert response.status_code == 502
    assert response.json() == {"detail": "Planet schedule is unavailable"}
