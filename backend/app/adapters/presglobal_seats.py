"""Read-only PresGlobal seat lookup for Cinema City, Planet, and Lev.

Status keys identify AVAILABLE seats, not occupied seats. Missing keys only
establish unavailability (they may be sold, held, or blocked by the cinema).
"""

import math
import re

import httpx

from app.adapters.base import ScreeningNotFoundError, SeatUnavailableError
from app.models.seat import Seat, SeatMap, build_seat_map

ORIGINS = {
    "cinema_city": "https://tickets.cinema-city.co.il",
    "yes_planet": "https://tickets5.planetcinema.co.il",
    "lev": "https://ticket.lev.co.il",
}


def numeric_id(value) -> str:
    value = str(value)
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("Invalid provider identifier")
    return value


def normalize(screening_id: str, layout: dict, status: dict) -> SeatMap:
    available = status["seats"]
    if not isinstance(available, dict) or status.get("error"):
        raise ValueError("Invalid seat status")
    seats = []
    for section_id, section in layout["S"].items():
        if section.get("r") != 1:
            raise ValueError("Unreserved seating has no assigned seat map")
        for group in section["G"].values():
            transform = group["rd"]
            angle = math.radians(float(transform.get("rotate", 0)))
            for row_id, row in group["R"].items():
                for seat_id, seat in row["S"].items():
                    key = f"{section_id}_{seat_id}_{row_id}"
                    cx, cy = float(seat["rd"]["cx"]), float(seat["rd"]["cy"])
                    x = float(transform["x"]) + cx * math.cos(angle) - cy * math.sin(angle)
                    y = float(transform["y"]) + cx * math.sin(angle) + cy * math.cos(angle)
                    if not math.isfinite(x) or not math.isfinite(y):
                        raise ValueError("Invalid seat coordinates")
                    kind = next(
                        (
                            name
                            for flag, name in (
                                ("hc", "accessible"),
                                ("co", "companion"),
                                ("pr", "premium"),
                                ("lv", "limited_view"),
                            )
                            if seat.get(flag)
                        ),
                        "standard",
                    )
                    seats.append(
                        Seat(
                            id=key,
                            section_id=section_id,
                            row=str(row["n"]),
                            number=str(seat["n"]),
                            x=x,
                            y=y,
                            kind=kind,
                            status="available" if key in available else "unavailable",
                        )
                    )
    if set(available) - {s.id for s in seats}:
        raise ValueError("Status refers to seats missing from layout")
    return build_seat_map(screening_id, seats)


async def get_seats(
    *,
    screening_id: str,
    chain: str,
    event_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SeatMap:
    try:
        event_id = numeric_id(event_id)
        origin = ORIGINS[chain]
        async with httpx.AsyncClient(
            base_url=origin,
            timeout=20,
            follow_redirects=False,
            transport=transport,
        ) as client:
            # Initialize an anonymous UUID exactly as the booking page does.
            # Never execute page scripts (some booking flows auto-select seats).
            page = await client.get(f"/order/{event_id}")
            if page.status_code == 404:
                raise ScreeningNotFoundError("Screening is no longer available")
            page.raise_for_status()
            uuid = client.cookies.get("uuid")
            if not uuid or not re.fullmatch(r"[a-fA-F0-9-]{36}", uuid):
                raise ValueError("Missing anonymous booking session")
            client.headers["uuid"] = uuid
            response = await client.get(f"/api/presentations/{event_id}")
            if response.status_code == 404:
                raise ScreeningNotFoundError("Screening is no longer available")
            response.raise_for_status()
            data = response.json()
            presentation = data["presentation"]
            if data.get("error") or not presentation:
                raise ScreeningNotFoundError("Screening is no longer available")
            if numeric_id(presentation["id"]) != event_id:
                raise ValueError("Presentation identity mismatch")
            if presentation["isReserved"] != 1:
                raise ValueError("Screening does not have assigned seating")
            response = await client.post(
                "/api/seats/seatplanV2",
                params={
                    "venueId": numeric_id(presentation["venueId"]),
                    "seatplanId": numeric_id(presentation["seatplanId"]),
                },
                json={},
            )
            response.raise_for_status()
            layout = response.json()
            response = await client.get(
                "/api/seats/seats-statusV2",
                params={
                    "presentationId": event_id,
                    "venueTypeId": numeric_id(presentation["venueTypeId"]),
                    "isReserved": 1,
                },
            )
            response.raise_for_status()
            result = normalize(screening_id, layout, response.json())
            client.cookies.clear()
            return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        raise SeatUnavailableError(f"{chain} seat map is unavailable") from None
