import asyncio
from datetime import date

from fastapi import APIRouter, Query

from app.adapters.base import ScheduleUnavailableError, ScreeningNotFoundError, SeatUnavailableError
from app.adapters.registry import registry
from app.adapters.seat_lookup import resolve_lookup
from app.data.cinemas import CINEMAS
from app.models.cinema import Cinema, Location
from app.models.screening import Screening
from app.models.search import (
    NearbyCinema,
    NearbyScreening,
    NearbySearchResponse,
    SeatAvailability,
)
from app.services.distance import haversine_km

router = APIRouter(prefix="/search", tags=["search"])
_SCHEDULE_CONCURRENCY = 4
_SEAT_CONCURRENCY = 4


def _nearby_cinemas(latitude: float, longitude: float, radius_km: float) -> list[tuple[Cinema, float]]:
    matches = [
        (
            cinema,
            haversine_km(latitude, longitude, cinema.latitude, cinema.longitude),
        )
        for cinema in CINEMAS
    ]
    return sorted(
        ((cinema, distance) for cinema, distance in matches if distance <= radius_km),
        key=lambda match: match[1],
    )


async def _get_screenings(cinema: Cinema, day: date) -> tuple[list[Screening], str]:
    if not cinema.schedule_supported:
        return [], "unsupported"
    adapter = registry.get(cinema.chain)
    if adapter is None:
        return [], "unsupported"
    try:
        return await adapter.get_screenings(cinema=cinema, date=day), "available"
    except ScheduleUnavailableError:
        return [], "unavailable"


async def _get_seat_availability(screening: Screening, seats_supported: bool) -> NearbyScreening:
    if not seats_supported:
        return NearbyScreening(screening=screening, seat_status="unsupported")
    try:
        lookup = resolve_lookup(screening.id)
        adapter = registry.get(lookup.chain)
        if adapter is None:
            raise ScreeningNotFoundError("Unknown cinema chain")
        async with asyncio.timeout(60):
            seat_map = await adapter.get_seats(screening=lookup)
    except (ScreeningNotFoundError, SeatUnavailableError, TimeoutError):
        return NearbyScreening(screening=screening, seat_status="unavailable")
    return NearbyScreening(
        screening=screening,
        seat_status="available",
        seat_availability=SeatAvailability(
            total=seat_map.total,
            available=seat_map.available,
            occupied=seat_map.occupied,
            held=seat_map.held,
            unavailable=seat_map.unavailable,
            unknown=seat_map.unknown,
        ),
    )


@router.get("", response_model=NearbySearchResponse)
async def search_nearby_cinemas(
    date: date,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=35, gt=0, le=100),
) -> NearbySearchResponse:
    """Find catalog cinemas in range, then fetch their schedules and seat summaries."""
    nearby = _nearby_cinemas(latitude, longitude, radius_km)
    schedule_semaphore = asyncio.Semaphore(_SCHEDULE_CONCURRENCY)

    async def load_schedule(cinema: Cinema) -> tuple[list[Screening], str]:
        async with schedule_semaphore:
            return await _get_screenings(cinema, date)

    schedule_results = await asyncio.gather(*(load_schedule(cinema) for cinema, _ in nearby))
    seat_semaphore = asyncio.Semaphore(_SEAT_CONCURRENCY)

    async def load_seats(screening: Screening, seats_supported: bool) -> NearbyScreening:
        async with seat_semaphore:
            return await _get_seat_availability(screening, seats_supported)

    seat_tasks = [
        (cinema.id, load_seats(screening, cinema.seats_supported))
        for (cinema, _), (screenings, _) in zip(nearby, schedule_results, strict=True)
        for screening in screenings
    ]
    loaded_seats = await asyncio.gather(*(task for _, task in seat_tasks))
    seats_by_cinema: dict[str, list[NearbyScreening]] = {cinema.id: [] for cinema, _ in nearby}
    for (cinema_id, _), seat_result in zip(seat_tasks, loaded_seats, strict=True):
        seats_by_cinema[cinema_id].append(seat_result)

    cinemas = []
    for (cinema, distance), (_, schedule_status) in zip(nearby, schedule_results, strict=True):
        cinemas.append(
            NearbyCinema(
                cinema=cinema,
                distance_km=round(distance, 2),
                schedule_status=schedule_status,
                screenings=seats_by_cinema[cinema.id],
            )
        )

    return NearbySearchResponse(
        date=date,
        origin=Location(latitude=latitude, longitude=longitude),
        radius_km=radius_km,
        cinemas=cinemas,
    )
