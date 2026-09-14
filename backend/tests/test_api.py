from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cinemas_are_listed() -> None:
    response = client.get("/api/cinemas")
    assert response.status_code == 200
    chains = {cinema["chain"] for cinema in response.json()}
    assert chains == {"cinema_city", "hot_cinema", "yes_planet", "lev", "movieland"}


def test_unknown_screening_seats_return_not_found() -> None:
    response = client.get("/api/screenings/example/seats")
    assert response.status_code == 404
