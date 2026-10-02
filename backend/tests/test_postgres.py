from __future__ import annotations

import psycopg
import pytest

from app.postgres import DatabaseUnavailableError, PostgresStore


def test_connection_failure_does_not_expose_database_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "must-not-appear-in-errors"

    def fail_connect(*_: object, **__: object) -> None:
        raise psycopg.OperationalError(f"connection failed with password={secret}")

    monkeypatch.setattr(psycopg, "connect", fail_connect)
    store = PostgresStore(
        f"postgresql://tutorial:{secret}@localhost:5433/tutorial"
    )

    with pytest.raises(DatabaseUnavailableError) as caught:
        store.healthcheck()

    assert str(caught.value) == "database connection failed"
    assert caught.value.__cause__ is None
    assert secret not in str(caught.value)
