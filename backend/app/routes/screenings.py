from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.adapters.registry import registry
from app.data.cinemas import CINEMAS
from app.models.screening import Screening

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
        results.extend(await adapter.get_screenings(cinema=cinema, date=date))
    return sorted(results, key=lambda screening: screening.starts_at)


@router.get("/{screening_id}/seats")
async def get_seats(screening_id: str) -> dict[str, str]:
    # Seat adapters will be added after the schedule adapters. Returning an
    # explicit status is preferable to pretending that no seats exist.
    raise HTTPException(
        status_code=501,
        detail=f"Seat lookup is not implemented yet for screening {screening_id}",
    )

