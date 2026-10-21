from collections import Counter

from fastapi.testclient import TestClient

from app.data.cinema_catalog import CINEMA_CATALOG, CINEMA_CONFIG_BY_ID, CINEMAS
from app.main import app


def test_catalog_is_complete_and_has_unique_public_ids():
    assert Counter(cinema.chain for cinema in CINEMAS) == {
        "cinema_city": 8,
        "yes_planet": 6,
        "hot_cinema": 12,
        "movieland": 6,
        "lev": 7,
    }
    assert len({cinema.id for cinema in CINEMAS}) == len(CINEMAS) == len(CINEMA_CATALOG)
    assert CINEMA_CONFIG_BY_ID["yes-planet-ayalon"].schedule_id == "1025"
    assert CINEMA_CONFIG_BY_ID["hot-cinema-petah-tikva"].seat_site_id == 1194


def test_cinema_endpoint_returns_the_static_catalog_with_capabilities():
    response = TestClient(app).get("/api/cinemas")
    assert response.status_code == 200
    assert len(response.json()) == len(CINEMAS)
    lev_tel_aviv = next(cinema for cinema in response.json() if cinema["id"] == "lev-tel-aviv")
    assert lev_tel_aviv["schedule_supported"] is True
    assert lev_tel_aviv["seats_supported"] is True
