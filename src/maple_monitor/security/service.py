from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from maple_monitor.models import SecurityQuarantine, WorkItem
from maple_monitor.security.scanner import ScanResult, scan_untrusted


_SOURCE_REF_MAX_LENGTH: Final = 512
_REVIEWER_MAX_LENGTH: Final = 200
_NOTE_MAX_LENGTH: Final = 2_000
_CONTROL_CATEGORIES: Final = frozenset({"Cc", "Cf"})
_RELEASE_WORK_KIND: Final = "released_analysis"


class QuarantineNotFoundError(LookupError):
    """Raised when an audited review targets an unknown quarantine row."""


class QuarantineReviewConflictError(RuntimeError):
    """Raised when a review would overwrite immutable audit history."""


class QuarantineReleaseConflictError(RuntimeError):
    """Raised when a release task key already identifies different work."""


def _contains_control(value: str, *, allow_line_whitespace: bool = False) -> bool:
    allowed = "\n\r\t" if allow_line_whitespace else ""
    return any(
        character not in allowed and unicodedata.category(character) in _CONTROL_CATEGORIES
        for character in value
    )


def _validate_source_ref(source_ref: str) -> None:
    if not isinstance(source_ref, str):
        raise TypeError("source_ref must be a string")
    if (
        not source_ref
        or source_ref != source_ref.strip()
        or len(source_ref) > _SOURCE_REF_MAX_LENGTH
        or _contains_control(source_ref)
    ):
        raise ValueError(
            "source_ref must be a trimmed 1-512 character string without control characters"
        )


def _validate_audit_field(
    value: str,
    *,
    name: str,
    max_length: int,
    allow_line_whitespace: bool = False,
) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if (
        not value
        or value != value.strip()
        or len(value) > max_length
        or _contains_control(value, allow_line_whitespace=allow_line_whitespace)
    ):
        raise ValueError(
            f"{name} must be a trimmed 1-{max_length} character string without "
            "unsupported control characters"
        )


def _serialized_findings(result: ScanResult) -> list[dict[str, object]]:
    return [
        {
            "rule_id": finding.rule_id,
            "score": finding.score,
            "evidence_hash": finding.evidence_hash,
            "escaped_evidence": finding.escaped_evidence,
        }
        for finding in result.findings
    ]


def quarantine_if_needed(
    session: Session,
    source_ref: str,
    text: str,
    source_kind: str,
    threshold: int,
) -> bool:
    _validate_source_ref(source_ref)
    result = scan_untrusted(text, source_kind)
    decision = result.quarantined(threshold)
    if not decision:
        return False

    content_hash = hashlib.sha256(result.normalized_text.encode("utf-8")).hexdigest()
    statement = (
        insert(SecurityQuarantine)
        .values(
            id=uuid4(),
            source_kind=source_kind,
            source_ref=source_ref,
            content_hash=content_hash,
            findings=_serialized_findings(result),
            risk_score=result.risk_score,
            review_state="pending",
        )
        .on_conflict_do_nothing(
            constraint="security_quarantine_source_content_key",
        )
    )
    session.execute(statement)
    return True


def _release_payload(quarantine: SecurityQuarantine) -> dict[str, str]:
    return {
        "quarantine_id": str(quarantine.id),
        "source_kind": quarantine.source_kind,
        "source_ref": quarantine.source_ref,
    }


def _payload_hash(payload: dict[str, str]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ensure_release_work_item(session: Session, quarantine: SecurityQuarantine) -> None:
    task_key = f"released-analysis:{quarantine.id}:v1"
    payload = _release_payload(quarantine)
    payload_hash = _payload_hash(payload)
    statement = (
        insert(WorkItem)
        .values(
            task_key=task_key,
            kind=_RELEASE_WORK_KIND,
            state="pending",
            payload=payload,
            payload_hash=payload_hash,
            available_at=func.now(),
        )
        .on_conflict_do_nothing(index_elements=[WorkItem.task_key])
    )
    session.execute(statement)

    work_item = session.execute(select(WorkItem).where(WorkItem.task_key == task_key)).scalar_one()
    if (
        work_item.kind != _RELEASE_WORK_KIND
        or work_item.payload != payload
        or work_item.payload_hash != payload_hash
    ):
        raise QuarantineReleaseConflictError(
            f"release task key {task_key!r} already identifies different work"
        )


def release_quarantine(
    session: Session,
    quarantine_id: UUID,
    reviewer: str,
    note: str,
) -> bool:
    if not isinstance(quarantine_id, UUID):
        raise TypeError("quarantine_id must be a UUID")
    _validate_audit_field(
        reviewer,
        name="reviewer",
        max_length=_REVIEWER_MAX_LENGTH,
    )
    _validate_audit_field(
        note,
        name="note",
        max_length=_NOTE_MAX_LENGTH,
        allow_line_whitespace=True,
    )

    with session.begin_nested():
        quarantine = session.execute(
            select(SecurityQuarantine)
            .where(SecurityQuarantine.id == quarantine_id)
            .with_for_update()
        ).scalar_one_or_none()
        if quarantine is None:
            raise QuarantineNotFoundError(f"quarantine {quarantine_id} not found")

        if quarantine.review_state == "confirmed":
            raise QuarantineReviewConflictError(
                f"quarantine {quarantine_id} is confirmed and cannot be released"
            )
        if quarantine.review_state == "released":
            if quarantine.reviewer != reviewer or quarantine.note != note:
                raise QuarantineReviewConflictError(
                    f"quarantine {quarantine_id} was already reviewed with different audit data"
                )
        elif quarantine.review_state == "pending":
            quarantine.review_state = "released"
            quarantine.reviewer = reviewer
            quarantine.note = note
            quarantine.released_at = session.execute(select(func.now())).scalar_one()
            session.flush()
        else:
            raise QuarantineReviewConflictError(
                f"quarantine {quarantine_id} has unsupported review state "
                f"{quarantine.review_state!r}"
            )

        _ensure_release_work_item(session, quarantine)

    return True
