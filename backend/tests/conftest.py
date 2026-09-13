import httpx
import pytest


@pytest.fixture(autouse=True)
def block_live_provider_requests(monkeypatch):
    async def blocked(self, request):
        pytest.fail(f"Unexpected live HTTP request: {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
