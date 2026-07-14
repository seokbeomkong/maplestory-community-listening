from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

import pytest


KST = ZoneInfo("Asia/Seoul")


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2026, 7, 14, 6, 20, tzinfo=KST),
            datetime(2026, 7, 14, 6, 20, tzinfo=KST),
        ),
        (
            datetime(2026, 7, 14, 6, 19, 59, tzinfo=KST),
            datetime(2026, 7, 14, 0, 20, tzinfo=KST),
        ),
        (
            datetime(2026, 7, 14, 15, 45, tzinfo=KST),
            datetime(2026, 7, 14, 12, 20, tzinfo=KST),
        ),
        (
            datetime(2026, 7, 13, 15, 19, tzinfo=UTC),
            datetime(2026, 7, 13, 18, 20, tzinfo=KST),
        ),
    ],
)
def test_aligns_to_the_latest_exact_kst_slot(now: datetime, expected: datetime) -> None:
    from maple_monitor.collection.service import align_kst_slot

    slot = align_kst_slot(now, interval_hours=6, minute=20)

    assert slot == expected
    assert slot.tzinfo is KST
    assert slot.second == 0
    assert slot.microsecond == 0


class _UnresolvedTimezone(tzinfo):
    def utcoffset(self, value: datetime | None) -> timedelta | None:
        return None

    def dst(self, value: datetime | None) -> timedelta | None:
        return None


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 7, 14, 6, 20),
        datetime(2026, 7, 14, 6, 20, tzinfo=_UnresolvedTimezone()),
    ],
)
def test_slot_alignment_requires_a_resolved_timezone(now: datetime) -> None:
    from maple_monitor.collection.service import align_kst_slot

    with pytest.raises(ValueError, match="timezone-aware"):
        align_kst_slot(now, interval_hours=6, minute=20)


@pytest.mark.parametrize("interval", [0, 5, 25])
def test_slot_alignment_rejects_an_interval_that_does_not_partition_a_day(
    interval: int,
) -> None:
    from maple_monitor.collection.service import align_kst_slot

    with pytest.raises(ValueError, match="divide 24"):
        align_kst_slot(datetime(2026, 7, 14, tzinfo=KST), interval, 20)


@pytest.mark.parametrize("interval", [True, 6.0, "6"])
def test_slot_alignment_rejects_non_integer_intervals(interval: object) -> None:
    from maple_monitor.collection.service import align_kst_slot

    with pytest.raises(TypeError, match="interval_hours"):
        align_kst_slot(  # type: ignore[arg-type]
            datetime(2026, 7, 14, tzinfo=KST),
            interval,
            20,
        )


@pytest.mark.parametrize("minute", [-1, 60])
def test_slot_alignment_rejects_minutes_outside_the_clock(minute: int) -> None:
    from maple_monitor.collection.service import align_kst_slot

    with pytest.raises(ValueError, match="minute"):
        align_kst_slot(datetime(2026, 7, 14, tzinfo=KST), 6, minute)


@pytest.mark.parametrize("minute", [True, 20.0, "20"])
def test_slot_alignment_rejects_non_integer_minutes(minute: object) -> None:
    from maple_monitor.collection.service import align_kst_slot

    with pytest.raises(TypeError, match="minute"):
        align_kst_slot(  # type: ignore[arg-type]
            datetime(2026, 7, 14, tzinfo=KST),
            6,
            minute,
        )


def test_slot_alignment_redacts_datetime_underflow_as_validation_failure() -> None:
    from maple_monitor.collection.service import align_kst_slot

    with pytest.raises(ValueError, match="representable datetime range"):
        align_kst_slot(
            datetime(1, 1, 1, 0, 0, tzinfo=KST),
            interval_hours=6,
            minute=20,
        )
