"""Resolve public screening IDs without a database or a second schedule fetch."""

import re

from app.adapters.base import ScreeningNotFoundError
from app.models.seat import SeatLookup

# Public screening-ID branch components. Lev's booking site is 9 for Tel Aviv.
BRANCHES = {
    ("cinema_city", "1170"): "cinema-city-glilot",
    ("yes_planet", "1025"): "yes-planet-ayalon",
    ("hot_cinema", "14"): "hot-cinema-petah-tikva",
    ("movieland", "1290"): "movieland-karmiel",
    ("lev", "9"): "lev-tel-aviv",
}


def resolve_lookup(screening_id: str) -> SeatLookup:
    match = re.fullmatch(r"([a-z_]+):([0-9]{1,12}):([0-9]{1,12})", screening_id)
    if not match or tuple(match.groups()[:2]) not in BRANCHES:
        raise ScreeningNotFoundError("Unknown screening ID or cinema")
    chain, branch, _ = match.groups()
    return SeatLookup(id=screening_id, chain=chain, cinema_id=BRANCHES[chain, branch])


def validate_lookup(screening, *, expected_chain: str) -> tuple[str, str]:
    lookup = resolve_lookup(screening.id)
    if (
        lookup.chain != expected_chain
        or screening.chain != expected_chain
        or lookup.cinema_id != screening.cinema_id
    ):
        raise ScreeningNotFoundError("Screening does not match cinema")
    _, branch, event = screening.id.split(":")
    return branch, event
