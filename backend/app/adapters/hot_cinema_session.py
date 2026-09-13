"""Temporary anonymous Bigger Picture session for Hot Cinema read-only operations."""

import re

import httpx
from pydantic import SecretStr

API_URL = "https://pub-api-use1.biggerpicture.ai/ecomAPI/public/api"


class HotCinemaSessionError(Exception):
    """Session creation or a read-only operation failed."""


class HotCinemaSession:
    def __init__(self, *, site_id: int, transport: httpx.AsyncBaseTransport | None = None):
        self._site_id = site_id
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._token: SecretStr | None = None

    async def __aenter__(self):
        if self._client is not None:
            raise HotCinemaSessionError("Session is already open")
        self._client = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=False,
            transport=self._transport,
        )
        return self

    async def __aexit__(self, *args):
        client, self._client = self._client, None
        self._token = None
        if client is not None:
            client.cookies.clear()
            await client.aclose()

    async def _login(self):
        self._token = None
        response = await self._client.post(
            f"{API_URL}/sys/login",
            json={"siteId": self._site_id, "saleChannelCode": "WEB", "language": "he_IL"},
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
            raise HotCinemaSessionError("Hot Cinema session response is invalid")
        self._token = SecretStr(token)

    async def _read(self, path: str) -> list[dict]:
        if self._client is None:
            raise HotCinemaSessionError("Use the session inside an async with block")
        try:
            for attempt in range(2):
                if self._token is None:
                    await self._login()
                response = await self._client.get(
                    f"{API_URL}{path}",
                    headers={"Authorization": f"Bearer {self._token.get_secret_value()}"},
                )
                if response.status_code == 401:
                    self._token = None
                    if attempt == 0:
                        continue
                response.raise_for_status()
                data = response.json()
                # Bigger Picture omits list when it explicitly reports zero records.
                if isinstance(data, dict) and "list" not in data and data.get("recordCount") == 0:
                    data["list"] = []
                if (
                    not isinstance(data, dict)
                    or str(data.get("returnCode")) != "0"
                    or not isinstance(data.get("list"), list)
                    or not all(isinstance(row, dict) for row in data["list"])
                ):
                    raise HotCinemaSessionError("Hot Cinema read response is invalid")
                return data["list"]
        except (httpx.HTTPError, ValueError):
            self._token = None
            # Do not propagate response bodies or exceptions carrying Authorization headers.
            raise HotCinemaSessionError("Hot Cinema session request failed") from None

    @staticmethod
    def _id(value: str | int) -> str:
        value = str(value)
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("Expected a numeric provider identifier")
        return value

    async def get_event(self, event_code: str | int) -> list[dict]:
        """Read event details using the public schedule EventId (not internal ei)."""
        code = self._id(event_code)
        return await self._read(f"/cus/event/code/{self._site_id}-{code}/min?vsAvailable=true")

    async def get_seat_status(self, event_id: str | int) -> list[dict]:
        """Read raw status using the internal ei from get_event; never reserve seats."""
        return await self._read(f"/cus/event/{self._id(event_id)}/seatsStatus")
