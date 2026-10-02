from __future__ import annotations

from .config import Settings
from .postgres import PostgresStore


def main() -> None:
    settings = Settings.from_env()
    if settings.store_backend != "postgres":
        raise SystemExit("database migrations require APP_STORE=postgres")
    PostgresStore(settings.database_url).run_migrations()


if __name__ == "__main__":
    main()
