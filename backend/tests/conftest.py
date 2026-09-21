from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.config import Settings
from app.main import create_app
from app.store import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def app(store: InMemoryStore) -> FastAPI:
    return create_app(settings=Settings(store_backend="memory"), store=store)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as active_client:
            yield active_client
