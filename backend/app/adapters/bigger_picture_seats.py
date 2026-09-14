"""Bigger Picture's event layout plus its sparse sold/held-seat status feed."""

import math

import httpx

from app.adapters.base import ScreeningNotFoundError, SeatUnavailableError
from app.adapters.bigger_picture_session import BiggerPictureSession, BiggerPictureSessionError
from app.adapters.presglobal_seats import numeric_id
from app.models.seat import Seat, SeatMap, build_seat_map


def normalize(screening_id: str, event: dict, statuses: list[dict]) -> SeatMap:
    indexed = {}
    for status in statuses:
        key = f"{numeric_id(status['sec'])}_{numeric_id(status['x'])}_{numeric_id(status['y'])}"
        if key in indexed:
            raise ValueError("Duplicate seat status")
        sold = status.get("s", 0)
        if not isinstance(sold, (int, float)) or not math.isfinite(sold) or sold < 0:
            raise ValueError("Invalid sold status")
        indexed[key] = "occupied" if sold > 0 else "held" if status.get("e") else "available"
    seats = []
    for section in event["vsp"]["vsedl"]:
        if section["ir"] is not True:
            raise ValueError("Unreserved seating has no assigned seat map")
        section_id = numeric_id(section["vsi"])
        for seat in section["vssedl"]:
            if not isinstance(seat["id"], bool):
                raise TypeError("Invalid deleted-seat flag")
            if seat["id"]:
                continue
            if numeric_id(seat["vsi"]) != section_id:
                raise ValueError("Seat section mismatch")
            key = f"{section_id}_{numeric_id(seat['xc'])}_{numeric_id(seat['yc'])}"
            # Match the provider's grid, including offsets for gaps and wider seats.
            x = float(seat["xc"]) + float(seat.get("xop", 0)) / 100
            y = float(seat["yc"]) + float(seat.get("yop", 0)) / 100
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Invalid seat coordinates")
            kind = {1: "standard", 10: "accessible", 11: "companion", 1000: "premium"}.get(
                seat.get("vsai", 1),
                "other",
            )
            seats.append(
                Seat(
                    id=key,
                    section_id=section_id,
                    row=str(seat["rn"]),
                    number=str(seat["sn"]),
                    x=x,
                    y=y,
                    kind=kind,
                    status=indexed.get(key, "available"),
                )
            )
    if set(indexed) - {s.id for s in seats}:
        raise ValueError("Status refers to seats missing from layout")
    return build_seat_map(screening_id, seats)


async def get_seats(
    *,
    screening_id: str,
    site_id: int,
    event_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SeatMap:
    try:
        event_id = numeric_id(event_id)
        async with BiggerPictureSession(site_id=site_id, transport=transport) as session:
            events = await session.get_event(event_id)
            if not events:
                raise ScreeningNotFoundError("Screening is no longer available")
            if len(events) != 1 or events[0]["si"] != site_id:
                raise ValueError("Unexpected event identity")
            event = events[0]
            statuses = await session.get_seat_status(event["ei"])
            return normalize(screening_id, event, statuses)
    except (BiggerPictureSessionError, ValueError, KeyError, TypeError, AttributeError):
        raise SeatUnavailableError("Bigger Picture seat map is unavailable") from None
