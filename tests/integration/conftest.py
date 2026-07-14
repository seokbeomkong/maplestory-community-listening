from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def database_url() -> str:
    try:
        value = os.environ["DATABASE_URL"]
    except KeyError:
        pytest.fail("DATABASE_URL must point at the isolated PostgreSQL test database")
    url = make_url(value)
    if url.host not in {"127.0.0.1", "::1", "localhost"} or url.database != "maple_monitor_test":
        pytest.fail("integration tests require the local maple_monitor_test database")
    return value


@pytest.fixture(scope="session")
def db_engine(database_url: str) -> Iterator[Engine]:
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
