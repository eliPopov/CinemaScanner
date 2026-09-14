import asyncio
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.adapters.base import ScheduleUnavailableError, ScreeningNotFoundError, SeatUnavailableError
from app.adapters.registry import registry
from app.adapters.seat_lookup import resolve_lookup
from app.data.cinemas import CINEMAS
from app.models.screening import Screening
from app.models.seat import SeatMap

router = APIRouter(prefix="/screenings", tags=["screenings"])


@router.get("", response_model=list[Screening])
async def list_screenings(
    date: date,
    chain: str | None = Query(default=None),
    cinema_id: str | None = Query(default=None),
) -> list[Screening]:
    cinemas = [cinema for cinema in CINEMAS if chain is None or cinema.chain == chain]
    if cinema_id is not None:
        cinemas = [cinema for cinema in cinemas if cinema.id == cinema_id]

    results: list[Screening] = []
    for cinema in cinemas:
        adapter = registry.get(cinema.chain)
        if adapter is None:
            continue
        try:
            results.extend(await adapter.get_screenings(cinema=cinema, date=date))
        except ScheduleUnavailableError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    return sorted(results, key=lambda screening: screening.starts_at)


@router.get("/{screening_id}/seats", response_model=SeatMap)
async def get_seats(screening_id: str) -> SeatMap:
    try:
        lookup = resolve_lookup(screening_id)
        adapter = registry.get(lookup.chain)
        if adapter is None:
            raise ScreeningNotFoundError("Unknown cinema chain")
        async with asyncio.timeout(60):
            return await adapter.get_seats(screening=lookup)
    except ScreeningNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (SeatUnavailableError, TimeoutError):
        raise HTTPException(status_code=502, detail="Provider seat map is unavailable") from None
