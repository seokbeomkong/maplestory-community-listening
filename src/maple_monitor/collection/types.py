from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PostListItem:
    board_id: int
    post_id: int
    analysis_unit: str
    category: str
    title: str
    published_at: datetime
    views: int
    recommendations: int
    comments: int
    source_url: str
    is_notice: bool
    is_ad: bool


@dataclass(frozen=True)
class CollectionSummary:
    """Counts observations handled by one caller-owned collection transaction.

    ``inserted`` and ``updated`` count canonical post identities written. ``quarantined``
    counts unique title observations whose scan decision is quarantine, including an
    idempotent replay. ``rejected`` counts invalid observations and duplicate observations
    collapsed into a canonical identity.
    """

    inserted: int
    updated: int
    quarantined: int
    rejected: int
