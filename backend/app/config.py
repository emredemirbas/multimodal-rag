from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    store_backend: str = "postgres"
    database_url: str = "postgresql://tutorial:tutorial@postgres:5432/tutorial"
    log_level: str = "INFO"
    embedding_dimensions: int = 64
    retrieval_limit: int = 4

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
        )
