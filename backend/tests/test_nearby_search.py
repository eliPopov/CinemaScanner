from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.adapters.registry import registry
from app.main import app
from app.models.cinema import Cinema
from app.models.screening import Movie, Screening
from app.models.seat import Seat, build_seat_map
from app.routes import search as search_route
from app.services.distance import haversine_km


def test_haversine_distance():
    assert haversine_km(32.1, 34.8, 32.1, 34.8) == 0
    assert haversine_km(0, 0, 1, 0) == pytest.approx(111.2, abs=0.1)


def test_nearby_search_groups_cinemas_and_includes_seat_counts(monkeypatch):
    supported = Cinema(
        id="yes-planet-ayalon",
        chain="yes_planet",
        name="Nearby cinema",
        address="Address",
        latitude=32.1,
        longitude=34.8,
        schedule_supported=True,
        seats_supported=True,
    )
    unsupported = Cinema(
        id="cinema-city-glilot",
        chain="cinema_city",
        name="Nearby unsupported cinema",
        address="Address",
        latitude=32.11,
        longitude=34.8,
    )
    outside_radius = supported.model_copy(
        update={"id": "yes-planet-haifa", "name": "Far cinema", "latitude": 32.8}
    )
    monkeypatch.setattr(search_route, "CINEMAS", (unsupported, supported, outside_radius))

    class Adapter:
        chain = "yes_planet"

        async def get_screenings(self, *, cinema, date):
            assert cinema.id == supported.id
            assert date == date_from_request
            return [
                Screening(
                    id="yes_planet:1025:123",
                    chain="yes_planet",
                    cinema_id=cinema.id,
                    cinema_name=cinema.name,
                    movie=Movie(id="yes_planet:movie", title="Movie"),
                    starts_at=datetime(2026, 10, 21, 20, tzinfo=ZoneInfo("Asia/Jerusalem")),
                    booking_url="https://tickets5.planetcinema.co.il/api/order/123",
                )
            ]

        async def get_seats(self, *, screening):
            assert screening.id == "yes_planet:1025:123"
            return build_seat_map(
                screening.id,
                [
                    Seat(id="1", row="A", number="1", status="available"),
                    Seat(id="2", row="A", number="2", status="occupied"),
                ],
            )

    date_from_request = date(2026, 10, 21)
    monkeypatch.setattr(registry, "_adapters", {"yes_planet": Adapter()})

    response = TestClient(app).get(
        "/api/search",
        params={
            "date": date_from_request.isoformat(),
            "latitude": 32.1,
            "longitude": 34.8,
            "radius_km": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [cinema["cinema"]["id"] for cinema in body["cinemas"]] == [
        "yes-planet-ayalon",
        "cinema-city-glilot",
    ]
    nearby_screening = body["cinemas"][0]["screenings"][0]
    assert nearby_screening["seat_status"] == "available"
    assert nearby_screening["seat_availability"] == {
        "total": 2,
        "available": 1,
        "occupied": 1,
        "held": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    assert body["cinemas"][1]["schedule_status"] == "unsupported"


def test_nearby_search_validates_coordinates_and_radius():
    client = TestClient(app)
    assert client.get("/api/search?date=2026-10-21&latitude=91&longitude=34.8").status_code == 422
    assert client.get("/api/search?date=2026-10-21&latitude=32.1&longitude=34.8&radius_km=0").status_code == 422
