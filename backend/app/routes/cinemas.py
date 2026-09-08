from fastapi import APIRouter, Query

from app.data.cinemas import CINEMAS
from app.models.cinema import Cinema

router = APIRouter(prefix="/cinemas", tags=["cinemas"])


@router.get("", response_model=list[Cinema])
async def list_cinemas(
    chain: str | None = Query(default=None),
) -> list[Cinema]:
    if chain is None:
        return CINEMAS
    return [cinema for cinema in CINEMAS if cinema.chain == chain]

