from __future__ import annotations

from collections.abc import AsyncIterator
import os
from typing import Mapping

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

# `app.main` constructs the ASGI application at import time and intentionally
# fails closed when development authentication has no configured token.
os.environ.setdefault("DEVELOPMENT_AUTH_TOKEN", "test-development-token")

from app.auth import AuthenticationError, Authenticator
from app.config import Settings
from app.main import create_app
from app.models import AuthenticatedPrincipal
from app.store import InMemoryStore


TEST_TOKENS = {
    "tenant-a-token-long-enough": AuthenticatedPrincipal(
        provider="test",
        subject="user-a",
        tenant_id="tenant-a",
    ),
    "tenant-b-token-long-enough": AuthenticatedPrincipal(
        provider="test",
        subject="user-b",
        tenant_id="tenant-b",
    ),
}


def auth_headers(tenant: str = "tenant-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {tenant}-token-long-enough"}


class MappingAuthenticator(Authenticator):
    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedPrincipal:
        authorization = headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer":
            raise AuthenticationError()
        principal = TEST_TOKENS.get(token)
        if principal is None:
            raise AuthenticationError(code="invalid_authentication")
        return principal


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def app(store: InMemoryStore) -> FastAPI:
    return create_app(
        settings=Settings(
            environment="test",
            store_backend="memory",
            development_auth_token="test-development-token",
        ),
        store=store,
        authenticator=MappingAuthenticator(),
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as active_client:
            yield active_client
