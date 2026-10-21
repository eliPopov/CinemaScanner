"""Resolve public screening IDs without a database or a second schedule fetch."""

import re

from app.adapters.base import ScreeningNotFoundError
from app.data.cinema_catalog import CINEMA_CATALOG
from app.models.seat import SeatLookup

# Public screening-ID branch components. Lev's `data-siteid` identifies the
# auditorium/building in the booking system, so it varies between screenings at
# the same Tel Aviv branch. These values are returned by the public Tel Aviv
# schedule and must all resolve to the configured cinema.
BRANCHES = {
    (config.cinema.chain, str(config.schedule_id)): config.cinema.id
    for config in CINEMA_CATALOG
    if config.cinema.seats_supported
    and config.schedule_id is not None
    and config.cinema.chain != "lev"
}
# Lev's `data-siteid` identifies an auditorium/building rather than its public
# branch. It varies by Tel Aviv screening; the public schedule currently emits
# these IDs for that configured branch.
BRANCHES.update({("lev", str(site_id)): "lev-tel-aviv" for site_id in range(5, 11)})


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
