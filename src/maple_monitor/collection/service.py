from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import islice
from typing import Final
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from maple_monitor.collection.repository import (
    ensure_supported_board,
    upsert_post,
    upsert_snapshot,
)
from maple_monitor.collection.types import CollectionSummary, PostListItem
from maple_monitor.config import LoadedSettings
from maple_monitor.security.service import quarantine_if_needed


KST: Final = ZoneInfo("Asia/Seoul")
SUPPORTED_BOARD_ID: Final = 2294
SUPPORTED_ANALYSIS_UNIT: Final = "hero"
SUPPORTED_CATEGORY: Final = "히어로"
MAX_ITEMS_PER_SLOT: Final = 5_000
MAX_TITLE_CHARACTERS: Final = 500
_CONFIG_VERSION = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BIGINT: Final = 2**63 - 1
_MAX_INTEGER: Final = 2**31 - 1


def align_kst_slot(now: datetime, interval_hours: int, minute: int) -> datetime:
    """Return the latest schedule boundary in Korea Standard Time."""

    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    if isinstance(interval_hours, bool) or not isinstance(interval_hours, int):
        raise TypeError("interval_hours must be an integer")
    if interval_hours < 1 or interval_hours > 24 or 24 % interval_hours:
        raise ValueError("interval_hours must divide 24")
    if isinstance(minute, bool) or not isinstance(minute, int):
        raise TypeError("minute must be an integer")
    if not 0 <= minute <= 59:
        raise ValueError("minute must be between 0 and 59")

    try:
        local = now.astimezone(KST)
        candidate = local.replace(
            hour=(local.hour // interval_hours) * interval_hours,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if candidate > local:
            candidate -= timedelta(hours=interval_hours)
    except OverflowError:
        raise ValueError("slot is outside the representable datetime range") from None
    return candidate


def _validate_collection_context(
    board_id: int,
    slot: datetime,
    loaded_settings: LoadedSettings,
) -> datetime:
    if isinstance(board_id, bool) or not isinstance(board_id, int):
        raise TypeError("board_id must be an integer")
    if board_id != SUPPORTED_BOARD_ID:
        raise ValueError("unsupported board")
    if not isinstance(loaded_settings, LoadedSettings):
        raise TypeError("loaded_settings must be validated settings")
    if _CONFIG_VERSION.fullmatch(loaded_settings.config_version) is None:
        raise ValueError("config_version must be a lowercase SHA-256 digest")
    if not isinstance(slot, datetime) or slot.tzinfo is None or slot.utcoffset() is None:
        raise ValueError("slot must be a timezone-aware datetime")

    collection = loaded_settings.settings.collection
    aligned = align_kst_slot(
        slot,
        interval_hours=collection.interval_hours,
        minute=collection.slot_minute_kst,
    )
    if slot != aligned:
        raise ValueError("slot must be an exact aligned KST slot")
    return aligned


def _bounded_observations(items: Iterable[PostListItem]) -> list[object]:
    if isinstance(items, (str, bytes, bytearray)):
        raise TypeError("items must be an iterable of PostListItem values")
    try:
        values = list(islice(iter(items), MAX_ITEMS_PER_SLOT + 1))
    except TypeError:
        raise TypeError("items must be an iterable of PostListItem values") from None
    if len(values) > MAX_ITEMS_PER_SLOT:
        raise ValueError("items exceed the per-slot observation limit")
    return values


def _is_nonnegative_integer(value: object, *, maximum: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and 0 <= value <= maximum


def _is_database_safe_text(value: str) -> bool:
    if "\x00" in value:
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def _is_representable_aware_datetime(value: object) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        if value.utcoffset() is None:
            return False
        value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError):
        return False
    return True


def _validated_actual_fetch_time(fetched_at: object) -> datetime:
    if not _is_representable_aware_datetime(fetched_at):
        raise ValueError("fetched_at must be a representable timezone-aware datetime")
    assert isinstance(fetched_at, datetime)
    return fetched_at.astimezone(UTC)


def _is_valid_item(item: object, board_id: int) -> bool:
    if not isinstance(item, PostListItem):
        return False
    if item.board_id != board_id:
        return False
    if not _is_nonnegative_integer(item.post_id, maximum=_MAX_BIGINT) or item.post_id == 0:
        return False
    if item.analysis_unit != SUPPORTED_ANALYSIS_UNIT or item.category != SUPPORTED_CATEGORY:
        return False
    if (
        not isinstance(item.title, str)
        or not item.title
        or item.title != item.title.strip()
        or len(item.title) > MAX_TITLE_CHARACTERS
        or not _is_database_safe_text(item.title)
    ):
        return False
    if not _is_representable_aware_datetime(item.published_at):
        return False
    if not _is_nonnegative_integer(item.views, maximum=_MAX_BIGINT):
        return False
    if not _is_nonnegative_integer(item.recommendations, maximum=_MAX_INTEGER):
        return False
    if not _is_nonnegative_integer(item.comments, maximum=_MAX_INTEGER):
        return False
    expected_url = f"https://www.inven.co.kr/board/maple/{item.board_id}/{item.post_id}"
    if item.source_url != expected_url:
        return False
    if not isinstance(item.is_notice, bool) or not isinstance(item.is_ad, bool):
        return False
    return not (item.is_notice and item.is_ad)


def _canonical_observation(items: list[PostListItem]) -> PostListItem:
    canonical = max(
        items,
        key=lambda item: (
            item.published_at.astimezone(UTC),
            item.title.encode("utf-8"),
            item.analysis_unit.encode("utf-8"),
            item.category.encode("utf-8"),
            item.source_url.encode("utf-8"),
            item.is_notice,
            item.is_ad,
        ),
    )
    return replace(
        canonical,
        views=max(item.views for item in items),
        recommendations=max(item.recommendations for item in items),
        comments=max(item.comments for item in items),
    )


def collect_board_slot(
    session: Session,
    board_id: int,
    items: Iterable[PostListItem],
    slot: datetime,
    loaded_settings: LoadedSettings,
    *,
    fetched_at: datetime,
) -> CollectionSummary:
    """Persist one bounded observation batch inside the caller-owned transaction."""

    canonical_slot = _validate_collection_context(board_id, slot, loaded_settings)
    actual_fetch_time = _validated_actual_fetch_time(fetched_at)
    observations = _bounded_observations(items)
    grouped: dict[int, list[PostListItem]] = {}
    rejected = 0
    for observation in observations:
        if not _is_valid_item(observation, board_id):
            rejected += 1
            continue
        assert isinstance(observation, PostListItem)
        grouped.setdefault(observation.post_id, []).append(observation)

    accepted: list[tuple[PostListItem, tuple[str, ...]]] = []
    for post_id in sorted(grouped):
        duplicates = grouped[post_id]
        rejected += len(duplicates) - 1
        accepted.append(
            (
                _canonical_observation(duplicates),
                tuple(sorted({item.title for item in duplicates})),
            )
        )

    ensure_supported_board(session)
    inserted = 0
    updated = 0
    quarantined = 0
    threshold = loaded_settings.settings.security.quarantine_threshold
    for item, observed_titles in accepted:
        source_ref = f"post:{item.board_id}:{item.post_id}"
        quarantined += sum(
            quarantine_if_needed(
                session,
                source_ref=source_ref,
                text=title,
                source_kind="title",
                threshold=threshold,
            )
            for title in observed_titles
        )
        if upsert_post(
            session,
            item,
            observed_at_slot_kst=canonical_slot,
        ):
            inserted += 1
        else:
            updated += 1
        upsert_snapshot(
            session,
            item,
            observed_at_slot_kst=canonical_slot,
            observed_at_actual=actual_fetch_time,
            config_version=loaded_settings.config_version,
        )

    return CollectionSummary(
        inserted=inserted,
        updated=updated,
        quarantined=quarantined,
        rejected=rejected,
    )
