from app.adapters.base import CinemaAdapter


class AdapterRegistry:
    def __init__(self, adapters: list[CinemaAdapter] | None = None) -> None:
        self._adapters = {adapter.chain: adapter for adapter in adapters or []}

    def get(self, chain: str) -> CinemaAdapter | None:
        return self._adapters.get(chain)

    def chains(self) -> list[str]:
        return sorted(self._adapters)


# Adapters will be registered here as each chain integration is implemented.
registry = AdapterRegistry()

