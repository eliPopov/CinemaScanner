from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import ScreeningNotFoundError, SeatUnavailableError
from app.adapters.bigger_picture_seats import normalize as normalize_bp
from app.adapters.cinema_city import CinemaCityAdapter
from app.adapters.hot_cinema import HotCinemaAdapter
from app.adapters.lev import LevAdapter
from app.adapters.movieland import MovielandAdapter
from app.adapters.presglobal_seats import ORIGINS
from app.adapters.presglobal_seats import normalize as normalize_pres
from app.adapters.registry import registry
from app.adapters.seat_lookup import resolve_lookup
from app.adapters.yes_planet import YesPlanetAdapter
from app.main import app

UUID = "11111111-1111-4111-8111-111111111111"
LAYOUT = {
    "S": {
        "1": {
            "r": 1,
            "G": {
                "0": {
                    "rd": {"x": 100, "y": 20, "rotate": 90},
                    "R": {
                        "4": {
                            "n": "A",
                            "S": {
                                "2": {"n": "10", "rd": {"cx": 60, "cy": -30}, "hc": 1},
                                "3": {"n": "9", "rd": {"cx": 120, "cy": -30}},
                            },
                        }
                    },
                }
            },
        }
    }
}
EVENT = {
    "si": 1194,
    "ei": 123,
    "vsp": {
        "vsedl": [
            {
                "vsi": 1,
                "ir": True,
                "vssedl": [
                    {"id": False, "vsi": 1, "rn": "A", "sn": str(x), "xc": x, "yc": 1}
                    for x in range(1, 4)
                ]
                + [{"id": True}],
            }
        ]
    },
}


@pytest.mark.parametrize(
    "adapter_class,chain,branch",
    [
        (CinemaCityAdapter, "cinema_city", "1170"),
        (YesPlanetAdapter, "yes_planet", "1025"),
        (LevAdapter, "lev", "9"),
    ],
)
async def test_presglobal_read_only_session_and_mapping(adapter_class, chain, branch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        assert str(request.url).startswith(ORIGINS[chain] + "/")
        if request.url.path == "/order/123":
            assert "uuid" not in request.headers
            return httpx.Response(200, headers={"set-cookie": f"uuid={UUID}; Path=/"})
        assert request.headers["uuid"] == UUID
        if request.url.path == "/api/presentations/123":
            return httpx.Response(
                200,
                json={
                    "presentation": {
                        "id": 123,
                        "venueId": 6,
                        "seatplanId": 1,
                        "venueTypeId": 30,
                        "isReserved": 1,
                    }
                },
            )
        if request.url.path == "/api/seats/seatplanV2":
            assert request.method == "POST"
            assert request.content == b"{}"
            assert request.url.params == httpx.QueryParams(venueId=6, seatplanId=1)
            return httpx.Response(200, json=LAYOUT)
        assert request.url.path == "/api/seats/seats-statusV2"
        assert request.url.params["venueTypeId"] == "30"
        return httpx.Response(200, json={"seats": {"1_2_4": 0}})

    adapter = adapter_class(transport=httpx.MockTransport(handler))
    result = await adapter.get_seats(screening=resolve_lookup(f"{chain}:{branch}:123"))
    assert (result.total, result.available, result.unavailable, result.occupied) == (2, 1, 1, 0)
    seat = result.seats[0]
    assert (seat.row, seat.number, seat.kind) == ("A", "10", "accessible")
    assert seat.x == pytest.approx(130)
    assert seat.y == pytest.approx(80)
    assert result.fetched_at.tzinfo is not None
    assert calls == [
        ("GET", "/order/123"),
        ("GET", "/api/presentations/123"),
        ("POST", "/api/seats/seatplanV2"),
        ("GET", "/api/seats/seats-statusV2"),
    ]


@pytest.mark.parametrize(
    "adapter_class,chain,branch,site",
    [
        (HotCinemaAdapter, "hot_cinema", "14", 1194),
        (MovielandAdapter, "movieland", "1290", 1290),
    ],
)
async def test_bigger_picture_layout_status_and_temporary_session(
    adapter_class, chain, branch, site
):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/sys/login"):
            assert b'"siteId":' + str(site).encode() in request.content
            return httpx.Response(200, json={"token": "temporary-test-token"})
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer temporary-test-token"
        if request.url.path.endswith(f"/event/code/{site}-123/min"):
            event = deepcopy(EVENT)
            event["si"] = site
            return httpx.Response(200, json={"returnCode": 0, "list": [event]})
        assert request.url.path.endswith("/event/123/seatsStatus")
        return httpx.Response(
            200,
            json={
                "returnCode": 0,
                "list": [
                    {"sec": 1, "x": 1, "y": 1, "s": 1},
                    {"sec": 1, "x": 2, "y": 1, "e": "2026-09-14T23:00:00"},
                ],
            },
        )

    result = await adapter_class(transport=httpx.MockTransport(handler)).get_seats(
        screening=resolve_lookup(f"{chain}:{branch}:123"),
    )
    assert (result.total, result.available, result.occupied, result.held) == (3, 1, 1, 1)
    assert len(calls) == 3
    assert "temporary-test-token" not in result.model_dump_json()


def test_empty_sparse_status_means_no_reported_sold_or_held_seats_with_valid_layout():
    result = normalize_bp("hot_cinema:14:123", EVENT, [])
    assert result.total == result.available == 3
    with pytest.raises(ValueError):
        normalize_bp("hot_cinema:14:123", {"vsp": {"vsedl": []}}, [])


@pytest.mark.parametrize("bad_status", [{}, {"seats": []}, {"seats": {"1_99_4": 0}}])
def test_presglobal_rejects_malformed_or_mismatched_status(bad_status):
    with pytest.raises((ValueError, KeyError)):
        normalize_pres("cinema_city:1170:123", LAYOUT, bad_status)


def test_presglobal_empty_availability_does_not_claim_occupied():
    result = normalize_pres("cinema_city:1170:123", LAYOUT, {"seats": {}})
    assert result.unavailable == 2
    assert result.occupied == result.available == 0


def test_bigger_picture_rejects_mismatched_status_and_duplicate_layout():
    with pytest.raises(ValueError):
        normalize_bp("x", EVENT, [{"sec": 9, "x": 1, "y": 1, "s": 1}])
    event = deepcopy(EVENT)
    event["vsp"]["vsedl"] *= 2
    with pytest.raises(ValueError):
        normalize_bp("x", event, [])


@pytest.mark.parametrize("status", [302, 403, 500])
async def test_presglobal_provider_failures_are_sanitized_and_redirects_not_followed(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"location": "https://untrusted.example/"},
            text="secret provider details",
        )

    with pytest.raises(SeatUnavailableError, match="seat map is unavailable") as exc:
        await LevAdapter(transport=httpx.MockTransport(handler)).get_seats(
            screening=resolve_lookup("lev:9:123"),
        )
    assert "secret" not in str(exc.value)
    assert len(calls) == 1


def test_seat_route_dispatches_without_schedule_fetch(monkeypatch):
    class Adapter:
        async def get_seats(self, *, screening):
            assert screening.id == "movieland:1290:123"
            return normalize_bp(screening.id, EVENT, [])

    monkeypatch.setitem(registry._adapters, "movieland", Adapter())
    response = TestClient(app).get("/api/screenings/movieland:1290:123/seats")
    assert response.status_code == 200
    assert response.json()["total"] == 3


@pytest.mark.parametrize(
    "error,code",
    [
        (SeatUnavailableError("sensitive upstream detail"), 502),
        (ScreeningNotFoundError("Screening is no longer available"), 404),
        (TimeoutError(), 502),
    ],
)
def test_seat_route_errors(monkeypatch, error, code):
    class Adapter:
        async def get_seats(self, *, screening):
            raise error

    monkeypatch.setitem(registry._adapters, "lev", Adapter())
    response = TestClient(app).get("/api/screenings/lev:9:123/seats")
    assert response.status_code == code
    assert "sensitive" not in response.text


@pytest.mark.parametrize(
    "screening_id", ["example", "lev:99:123", "movieland:1290:abc", "cinema_city:1170:123?url=evil"]
)
def test_unknown_or_malformed_ids_never_contact_providers(screening_id):
    with pytest.raises(ScreeningNotFoundError):
        resolve_lookup(screening_id)


@pytest.mark.parametrize(
    "failure", ["missing_uuid", "bad_presentation", "layout_403", "status_403"]
)
async def test_presglobal_never_returns_partial_maps(failure):
    def handler(request):
        if request.url.path == "/order/123":
            headers = {} if failure == "missing_uuid" else {"set-cookie": f"uuid={UUID}; Path=/"}
            return httpx.Response(200, headers=headers)
        if request.url.path == "/api/presentations/123":
            return httpx.Response(
                200,
                json={
                    "presentation": {
                        "id": 999 if failure == "bad_presentation" else 123,
                        "venueId": 9,
                        "seatplanId": 1,
                        "venueTypeId": 1,
                        "isReserved": 1,
                    }
                },
            )
        if request.url.path == "/api/seats/seatplanV2":
            return (
                httpx.Response(403) if failure == "layout_403" else httpx.Response(200, json=LAYOUT)
            )
        assert request.url.path == "/api/seats/seats-statusV2"
        return httpx.Response(403)

    with pytest.raises(SeatUnavailableError):
        await LevAdapter(transport=httpx.MockTransport(handler)).get_seats(
            screening=resolve_lookup("lev:9:123"),
        )


async def test_provider_missing_event_returns_not_found():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(ScreeningNotFoundError):
        await CinemaCityAdapter(transport=httpx.MockTransport(handler)).get_seats(
            screening=resolve_lookup("cinema_city:1170:123"),
        )


async def test_movieland_session_is_lazy_and_cleared_on_error():
    from app.data.cinemas import CINEMAS

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    adapter = MovielandAdapter(transport=httpx.MockTransport(handler))
    cinema = next(c for c in CINEMAS if c.chain == "movieland")
    session = adapter.open_session(cinema=cinema)
    assert calls == []
    from app.adapters.bigger_picture_session import BiggerPictureSessionError

    with pytest.raises(BiggerPictureSessionError):
        async with session:
            await session.get_event(123)
    assert session._client is session._token is None
