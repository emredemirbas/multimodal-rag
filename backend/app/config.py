from __future__ import annotations

from dataclasses import dataclass
import os


def _environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    store_backend: str = "postgres"
    database_url: str = "postgresql://tutorial:tutorial@postgres:5432/tutorial"
    log_level: str = "INFO"
    embedding_dimensions: int = 64
    retrieval_limit: int = 4
    auto_migrate: bool = True
    auth_mode: str = "development"
    development_auth_token: str = ""
    development_auth_subject: str = "local-user"
    development_auth_tenant: str = "local"
    trusted_proxy_secret: str = ""

    def __post_init__(self) -> None:
        environment = self.environment.strip().lower()
        auth_mode = self.auth_mode.strip().lower()
        if auth_mode == "development":
            if environment not in {"development", "test"}:
                raise ValueError(
                    "development authentication is allowed only in development or test"
                )
            if len(self.development_auth_token) < 16:
                raise ValueError(
                    "development authentication token must contain at least 16 characters"
                )
        elif auth_mode == "trusted_proxy":
            if len(self.trusted_proxy_secret) < 16:
                raise ValueError(
                    "AUTH_TRUSTED_PROXY_SECRET must contain at least 16 characters"
                )
        else:
            raise ValueError(f"unsupported AUTH_MODE: {self.auth_mode}")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("APP_ENV", "development"),
            store_backend=os.getenv("APP_STORE", "postgres"),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://tutorial:tutorial@postgres:5432/tutorial",
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "64")),
            retrieval_limit=int(os.getenv("RETRIEVAL_LIMIT", "4")),
            auto_migrate=_environment_flag("APP_AUTO_MIGRATE", True),
            auth_mode=os.getenv("AUTH_MODE", "development"),
            development_auth_token=os.getenv(
                "DEVELOPMENT_AUTH_TOKEN", ""
            ),
            development_auth_subject=os.getenv(
                "AUTH_DEVELOPMENT_SUBJECT", "local-user"
            ),
            development_auth_tenant=os.getenv("AUTH_DEVELOPMENT_TENANT", "local"),
            trusted_proxy_secret=os.getenv("AUTH_TRUSTED_PROXY_SECRET", ""),
        )
