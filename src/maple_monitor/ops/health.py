from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session


def database_health(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        value = connection.execute(text("SELECT 1")).scalar_one()
    return {"database": "ok" if value == 1 else "error"}


def collector_is_healthy(session: Session, *, now: datetime, max_age_hours: int) -> bool:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if isinstance(max_age_hours, bool) or not isinstance(max_age_hours, int):
        raise TypeError("max_age_hours must be an integer")
    if not 1 <= max_age_hours <= 168:
        raise ValueError("max_age_hours must be between 1 and 168")
    cutoff = now.astimezone(UTC) - timedelta(hours=max_age_hours)
    return bool(
        session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM collection_runs "
                "WHERE job_type LIKE 'metadata:%' AND status = 'succeeded' "
                "AND finished_at >= :cutoff)"
            ),
            {"cutoff": cutoff},
        ).scalar_one()
    )
