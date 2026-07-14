from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


def create_engine_from_env() -> Engine:
    return create_engine(
        os.environ["DATABASE_URL"],
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=1,
    )


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        with session.begin():
            yield session
