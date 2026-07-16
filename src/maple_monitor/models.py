from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Board(Base):
    __tablename__ = "boards"
    __table_args__ = (CheckConstraint("kind IN ('job', 'free', 'info')"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)


class Post(Base):
    __tablename__ = "posts"

    board_id: Mapped[int] = mapped_column(ForeignKey("boards.id"), primary_key=True)
    post_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    analysis_unit: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str] = mapped_column(Text)
    is_notice: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_ad: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    current_category: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PostMetricSnapshot(Base):
    __tablename__ = "post_metric_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["board_id", "post_id"],
            ["posts.board_id", "posts.post_id"],
        ),
        CheckConstraint("views >= 0"),
        CheckConstraint("recommendations >= 0"),
        CheckConstraint("comments >= 0"),
        {"postgresql_partition_by": "RANGE (observed_at_slot_kst)"},
    )

    board_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    observed_at_slot_kst: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    observed_at_actual: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    views: Mapped[int] = mapped_column(BigInteger)
    recommendations: Mapped[int] = mapped_column(Integer)
    comments: Mapped[int] = mapped_column(Integer)
    config_version: Mapped[str] = mapped_column(CHAR(64))


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    __table_args__ = (CheckConstraint("status IN ('running', 'succeeded', 'partial', 'failed')"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    job_type: Mapped[str] = mapped_column(Text)
    scheduled_at_slot_kst: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    config_version: Mapped[str] = mapped_column(CHAR(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diagnostics: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )


class RunSlot(Base):
    __tablename__ = "run_slots"

    job_type: Mapped[str] = mapped_column(Text, primary_key=True)
    scheduled_at_slot_kst: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("collection_runs.id")
    )


class SourceBackfillState(Base):
    __tablename__ = "source_backfill_states"
    __table_args__ = (
        CheckConstraint(
            "next_page > 0",
            name="source_backfill_states_next_page_check",
        ),
        CheckConstraint(
            "source_key IN ('warrior', 'magician', 'archer', 'thief', "
            "'pirate', 'free', 'qna', 'tips')",
            name="source_backfill_states_source_key_check",
        ),
        Index("source_backfill_states_updated_at_idx", "updated_at"),
    )

    source_key: Mapped[str] = mapped_column(Text, primary_key=True)
    next_page: Mapped[int] = mapped_column(Integer)
    checkpoint_post_id: Mapped[int | None] = mapped_column(BigInteger)
    complete: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint("state IN ('pending', 'leased', 'succeeded', 'retry', 'dead')"),
        Index("work_items_claim_idx", "state", "priority", "available_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, server_default=text("100"))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    payload_hash: Mapped[str | None] = mapped_column(CHAR(64))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class CumulativeTopPost(Base):
    __tablename__ = "cumulative_top_posts"
    __table_args__ = (
        PrimaryKeyConstraint(
            "analysis_unit",
            "metric",
            "as_of_slot_kst",
            "post_id",
            name="cumulative_top_posts_pkey",
        ),
        UniqueConstraint(
            "analysis_unit",
            "metric",
            "as_of_slot_kst",
            "rank",
            name="cumulative_top_posts_unit_metric_slot_rank_key",
        ),
        ForeignKeyConstraint(
            ["board_id", "post_id"],
            ["posts.board_id", "posts.post_id"],
            name="cumulative_top_posts_post_fkey",
        ),
        CheckConstraint(
            "metric IN ('views', 'recommendations', 'comments')",
            name="cumulative_top_posts_metric_check",
        ),
        CheckConstraint("rank > 0", name="cumulative_top_posts_rank_check"),
        CheckConstraint(
            "metric_value >= 0",
            name="cumulative_top_posts_metric_value_check",
        ),
    )

    analysis_unit: Mapped[str] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(Text)
    as_of_slot_kst: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rank: Mapped[int] = mapped_column(Integer)
    board_id: Mapped[int] = mapped_column(Integer)
    post_id: Mapped[int] = mapped_column(BigInteger)
    metric_value: Mapped[int] = mapped_column(BigInteger)
    config_version: Mapped[str] = mapped_column(CHAR(64))


Index(
    "cumulative_latest_idx",
    CumulativeTopPost.analysis_unit,
    CumulativeTopPost.metric,
    CumulativeTopPost.as_of_slot_kst.desc(),
    CumulativeTopPost.rank,
)


class SecurityQuarantine(Base):
    __tablename__ = "security_quarantine"
    __table_args__ = (
        UniqueConstraint(
            "source_kind",
            "source_ref",
            "content_hash",
            name="security_quarantine_source_content_key",
        ),
        CheckConstraint(
            "risk_score BETWEEN 0 AND 100",
            name="security_quarantine_risk_score_check",
        ),
        CheckConstraint(
            "review_state IN ('pending', 'released', 'confirmed')",
            name="security_quarantine_review_state_check",
        ),
        CheckConstraint(
            "source_kind ~ '^[a-z][a-z0-9_]{0,63}$'",
            name="security_quarantine_source_kind_check",
        ),
        CheckConstraint(
            "length(source_ref) BETWEEN 1 AND 512 AND source_ref = btrim(source_ref)",
            name="security_quarantine_source_ref_check",
        ),
        CheckConstraint(
            "jsonb_typeof(findings) = 'array'",
            name="security_quarantine_findings_array_check",
        ),
        CheckConstraint(
            "(review_state = 'pending' AND reviewer IS NULL AND note IS NULL "
            "AND released_at IS NULL) OR "
            "(review_state = 'released' AND reviewer IS NOT NULL AND btrim(reviewer) <> '' "
            "AND note IS NOT NULL AND btrim(note) <> '' AND released_at IS NOT NULL) OR "
            "(review_state = 'confirmed' AND reviewer IS NOT NULL AND btrim(reviewer) <> '' "
            "AND note IS NOT NULL AND btrim(note) <> '' AND released_at IS NULL)",
            name="security_quarantine_review_audit_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    source_kind: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(CHAR(64))
    findings: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    risk_score: Mapped[int] = mapped_column(Integer)
    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    review_state: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
