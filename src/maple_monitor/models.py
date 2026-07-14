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
    Text,
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
