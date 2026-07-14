from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from maple_monitor.db_safety import UnsafeTestDatabaseUrlError
from maple_monitor.db_safety import validate_isolated_test_database_url


def _require_isolated_test_database_url(value: str | None) -> None:
    try:
        validate_isolated_test_database_url(value)
    except UnsafeTestDatabaseUrlError as exc:
        pytest.fail(str(exc))


@pytest.fixture(scope="session", autouse=True)
def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    _require_isolated_test_database_url(value)
    assert value is not None
    return value


@pytest.fixture(scope="session")
def db_engine(database_url: str) -> Iterator[Engine]:
    _require_isolated_test_database_url(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError as exc:
        engine.dispose()
        pytest.fail(f"PostgreSQL test database is unavailable: {exc}")

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    with db_engine.connect() as connection:
        outer_transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        outer_transaction.rollback()
