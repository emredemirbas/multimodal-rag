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
    embedding_provider: str = 'hash'
    retrieval_limit: int = 4
    auto_migrate: bool = True
    auth_mode: str = "development"
    development_auth_token: str = ""
    development_auth_subject: str = "local-user"
    development_auth_tenant: str = "local"
    trusted_proxy_secret: str = ""
    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "tutorial-artifacts"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    broker_url: str = "redis://redis:6379/0"
    upload_limit_bytes: int = 2_000_000
    job_lease_seconds: int = 180
    youtube_api_key: str = ""
    playlist_concurrency: int = 2
    answer_provider: str = 'extractive'
    ollama_base_url: str = 'http://ollama:11434'
    ollama_model: str = 'qwen3:4b'
    local_model_timeout: int = 24

    def __post_init__(self) -> None:
        from .local_model import checked_local_url
        if self.embedding_provider not in {'hash', 'ollama'} or self.embedding_dimensions != 64:
            raise ValueError('Use hash (64-D) or local Ollama (fixed 1024-D); custom dimensions are disabled')
        if self.answer_provider not in {'extractive', 'ollama'}:
            raise ValueError('Only extractive and local Ollama answers are supported; no paid provider is configured')
        checked_local_url(self.ollama_base_url)
        if self.ollama_model != 'qwen3:4b' or not 1 <= self.local_model_timeout <= 24:
            raise ValueError('Use local qwen3:4b with a 1–24 second timeout')
        if not 1 <= self.playlist_concurrency <= 4:
            raise ValueError("PLAYLIST_CONCURRENCY must be between 1 and 4")
        if not 1 <= self.retrieval_limit <= 4:
            raise ValueError("RETRIEVAL_LIMIT must be between 1 and 4")
        if not 1 <= self.upload_limit_bytes <= 2_000_000:
            raise ValueError("UPLOAD_LIMIT_BYTES must be between 1 and 2000000")
        if self.job_lease_seconds < 180:
            raise ValueError("job lease must exceed the 120-second task hard limit")
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
            embedding_provider=os.getenv('EMBEDDING_PROVIDER', 'hash'),
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
            s3_endpoint=os.getenv("S3_ENDPOINT", "http://minio:9000"),
            s3_bucket=os.getenv("S3_BUCKET", "tutorial-artifacts"),
            s3_access_key=os.getenv("S3_ACCESS_KEY", ""),
            s3_secret_key=os.getenv("S3_SECRET_KEY", ""),
            broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
            upload_limit_bytes=int(os.getenv("UPLOAD_LIMIT_BYTES", "2000000")),
            job_lease_seconds=int(os.getenv("JOB_LEASE_SECONDS", "180")),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
            playlist_concurrency=int(os.getenv("PLAYLIST_CONCURRENCY", "2")),
            answer_provider=os.getenv('ANSWER_PROVIDER', 'extractive'),
            ollama_base_url=os.getenv('OLLAMA_BASE_URL', 'http://ollama:11434'),
            ollama_model=os.getenv('OLLAMA_MODEL', 'qwen3:4b'),
            local_model_timeout=int(os.getenv('LOCAL_MODEL_TIMEOUT', '24')),
        )
