from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, literal, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from maple_monitor.collection.types import PostListItem
from maple_monitor.models import Board, Post, PostMetricSnapshot
from maple_monitor.sources import SourceDefinition


class SnapshotConfigConflict(RuntimeError):
    """Raised when a snapshot slot is already pinned to another configuration."""


def ensure_supported_board(session: Session, source: SourceDefinition) -> None:
    statement = (
        insert(Board)
        .values(id=source.board_id, name=source.name, kind=source.kind)
        .on_conflict_do_nothing(index_elements=[Board.id])
    )
    session.execute(statement)


def highest_ordinary_post_id(session: Session, board_id: int) -> int | None:
    statement = (
        select(Post.post_id)
        .where(
            Post.board_id == board_id,
            Post.is_notice.is_(False),
            Post.is_ad.is_(False),
        )
        .order_by(Post.post_id.desc())
        .limit(1)
    )
    return session.execute(statement).scalar_one_or_none()


def upsert_post(
    session: Session,
    item: PostListItem,
    *,
    observed_at_actual: datetime,
) -> bool:
    """Insert or monotonically refresh a canonical post; return whether inserted."""

    values = {
        "board_id": item.board_id,
        "post_id": item.post_id,
        "analysis_unit": item.analysis_unit,
        "title": item.title,
        "published_at": item.published_at,
        "source_url": item.source_url,
        "is_notice": item.is_notice,
        "is_ad": item.is_ad,
        "current_category": item.category,
        "last_seen_at": observed_at_actual,
    }
    inserted_post_id = session.execute(
        insert(Post)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[Post.board_id, Post.post_id])
        .returning(Post.post_id)
    ).scalar_one_or_none()
    if inserted_post_id is not None:
        return True

    existing_rank = tuple_(
        Post.published_at,
        Post.title.collate("C"),
        Post.analysis_unit.collate("C"),
        func.coalesce(Post.current_category, "").collate("C"),
        Post.source_url.collate("C"),
        Post.is_notice,
        Post.is_ad,
    )
    candidate_rank = tuple_(
        literal(item.published_at),
        literal(item.title).collate("C"),
        literal(item.analysis_unit).collate("C"),
        literal(item.category).collate("C"),
        literal(item.source_url).collate("C"),
        literal(item.is_notice),
        literal(item.is_ad),
    )
    session.execute(
        update(Post)
        .where(
            Post.board_id == item.board_id,
            Post.post_id == item.post_id,
            or_(
                Post.last_seen_at < observed_at_actual,
                and_(
                    Post.last_seen_at == observed_at_actual,
                    existing_rank < candidate_rank,
                ),
            ),
        )
        .values(
            analysis_unit=item.analysis_unit,
            title=item.title,
            published_at=item.published_at,
            source_url=item.source_url,
            is_notice=item.is_notice,
            is_ad=item.is_ad,
            current_category=item.category,
            last_seen_at=observed_at_actual,
        )
    )
    return False


def upsert_snapshot(
    session: Session,
    item: PostListItem,
    *,
    observed_at_slot_kst: datetime,
    observed_at_actual: datetime,
    config_version: str,
) -> None:
    statement = insert(PostMetricSnapshot).values(
        board_id=item.board_id,
        post_id=item.post_id,
        observed_at_slot_kst=observed_at_slot_kst,
        observed_at_actual=observed_at_actual,
        views=item.views,
        recommendations=item.recommendations,
        comments=item.comments,
        config_version=config_version,
    )
    persisted_post_id = session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                PostMetricSnapshot.board_id,
                PostMetricSnapshot.post_id,
                PostMetricSnapshot.observed_at_slot_kst,
            ],
            set_={
                "observed_at_actual": func.greatest(
                    PostMetricSnapshot.observed_at_actual,
                    statement.excluded.observed_at_actual,
                ),
                "views": func.greatest(
                    PostMetricSnapshot.views,
                    statement.excluded.views,
                ),
                "recommendations": func.greatest(
                    PostMetricSnapshot.recommendations,
                    statement.excluded.recommendations,
                ),
                "comments": func.greatest(
                    PostMetricSnapshot.comments,
                    statement.excluded.comments,
                ),
            },
            where=(PostMetricSnapshot.config_version == statement.excluded.config_version),
        ).returning(PostMetricSnapshot.post_id)
    ).scalar_one_or_none()
    if persisted_post_id is None:
        raise SnapshotConfigConflict("snapshot slot belongs to another configuration")
