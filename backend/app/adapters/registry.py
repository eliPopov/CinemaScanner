from app.adapters.base import CinemaAdapter
from app.adapters.cinema_city import CinemaCityAdapter
from app.adapters.hot_cinema import HotCinemaAdapter
from app.adapters.lev import LevAdapter
from app.adapters.movieland import MovielandAdapter
from app.adapters.yes_planet import YesPlanetAdapter


class AdapterRegistry:
    def __init__(self, adapters: list[CinemaAdapter] | None = None) -> None:
        self._adapters = {adapter.chain: adapter for adapter in adapters or []}

    def get(self, chain: str) -> CinemaAdapter | None:
        return self._adapters.get(chain)

    def chains(self) -> list[str]:
        return sorted(self._adapters)


registry = AdapterRegistry(
    [CinemaCityAdapter(), YesPlanetAdapter(), HotCinemaAdapter(), LevAdapter(), MovielandAdapter()]
)
