from __future__ import annotations

import pytest

from app.auth import (
    AuthenticationError,
    DevelopmentAuthenticator,
    TrustedProxyAuthenticator,
)
from app.config import Settings
from app.main import build_authenticator, create_app
from app.store import InMemoryStore


def test_development_authenticator_requires_exact_bearer_token() -> None:
    authenticator = DevelopmentAuthenticator(
        token="development-token-long-enough",
        subject="developer",
        tenant_id="local",
    )

    principal = authenticator.authenticate(
        {"authorization": "Bearer development-token-long-enough"}
    )
    assert principal.subject == "developer"
    assert principal.tenant_id == "local"

    with pytest.raises(AuthenticationError):
        authenticator.authenticate({})
    with pytest.raises(AuthenticationError):
        authenticator.authenticate({"authorization": "Bearer wrong-token-long-enough"})


def test_development_authentication_fails_closed_outside_local_environments() -> None:
    with pytest.raises(ValueError, match="allowed only"):
        Settings(environment="production", auth_mode="development")


def test_auth_mode_is_case_insensitive() -> None:
    settings = Settings(
        environment="development",
        auth_mode=" Development ",
        development_auth_token="development-token-long-enough",
    )
    assert isinstance(build_authenticator(settings), DevelopmentAuthenticator)


def test_trusted_proxy_requires_secret_and_valid_identity_headers() -> None:
    authenticator = TrustedProxyAuthenticator(
        shared_secret="trusted-proxy-secret-long-enough"
    )
    headers = {
        "x-trusted-proxy-secret": "trusted-proxy-secret-long-enough",
        "x-authenticated-subject": "external-user-42",
        "x-authenticated-tenant": "tenant-a",
    }
    principal = authenticator.authenticate(headers)
    assert principal.provider == "trusted_proxy"
    assert principal.subject == "external-user-42"
    assert principal.tenant_id == "tenant-a"

    with pytest.raises(AuthenticationError):
        authenticator.authenticate({**headers, "x-trusted-proxy-secret": "wrong"})
    with pytest.raises(AuthenticationError):
        authenticator.authenticate({**headers, "x-authenticated-tenant": "invalid tenant"})


def test_authentication_secrets_have_a_minimum_length() -> None:
    with pytest.raises(ValueError, match="at least 16"):
        Settings(environment="development", development_auth_token="")
    with pytest.raises(ValueError, match="at least 16"):
        DevelopmentAuthenticator(token="short", subject="user", tenant_id="local")
    with pytest.raises(ValueError, match="at least 16"):
        TrustedProxyAuthenticator(shared_secret="short")


def test_openapi_describes_bearer_authentication() -> None:
    app = create_app(
        settings=Settings(
            environment="test",
            store_backend="memory",
            development_auth_token="test-development-token",
        ),
        store=InMemoryStore(),
    )
    schema = app.openapi()
    security_schemes = schema["components"]["securitySchemes"]
    assert security_schemes["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert schema["paths"]["/api/v1/projects"]["get"]["security"] == [
        {"HTTPBearer": []}
    ]


def test_settings_read_compose_auth_and_migration_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_AUTO_MIGRATE", "false")
    monkeypatch.setenv("DEVELOPMENT_AUTH_TOKEN", "configured-token-long-enough")
    settings = Settings.from_env()
    assert settings.auto_migrate is False
    assert settings.development_auth_token == "configured-token-long-enough"
