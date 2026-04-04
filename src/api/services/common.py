from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from statistics import mean
from typing import Any, Callable, Iterable, TypeVar

from sqlalchemy.orm import Session

from src.api.service_errors import DuplicateRequestError
from src.contracts.core import to_api_timestamp
from src.db.models import AppMetadata, DraftArtifact, Ticket, TicketRun
from src.orchestration.state import build_claim_projection

T = TypeVar("T")


@dataclass(frozen=True)
class EvaluationSummaryRefPayload:
    status: str
    trace_id: str
    has_response_quality: bool
    response_quality_overall_score: float | None
    has_trajectory_evaluation: bool
    trajectory_score: float | None
    trajectory_violation_count: int | None


@dataclass(frozen=True)
class TicketClaimProjectionPayload:
    claimed_by: str | None
    claimed_at: str | None
    lease_until: str | None


class IdempotencyService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_available(self, key: str) -> None:
        existing = self._session.get(AppMetadata, self._build_key(key))
        if existing is not None:
            raise DuplicateRequestError(key)

    def record(self, key: str, payload: dict[str, Any]) -> None:
        metadata_key = self._build_key(key)
        value = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        record = self._session.get(AppMetadata, metadata_key)
        if record is None:
            self._session.add(AppMetadata(key=metadata_key, value=value))
            return
        record.value = value

    def _build_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"idempotency:{digest}"


def _select_latest_run(runs: Iterable[TicketRun]) -> TicketRun | None:
    return _select_latest_by(
        runs,
        key=lambda item: (item.started_at or item.created_at, item.created_at, item.run_id),
    )


def _select_latest_snapshot_run(runs: Iterable[TicketRun]) -> TicketRun | None:
    return _select_latest_by(
        runs,
        key=lambda item: (item.created_at, item.run_id),
    )


def _select_latest_draft(drafts: Iterable[DraftArtifact]) -> DraftArtifact | None:
    return _select_latest_by(
        drafts,
        key=lambda item: (item.version_index, item.created_at, item.draft_id),
    )


def _select_latest_by(
    items: Iterable[T],
    *,
    key: Callable[[T], Any],
) -> T | None:
    ordered = sorted(items, key=key, reverse=True)
    return ordered[0] if ordered else None


def build_evaluation_summary_ref(run: TicketRun) -> EvaluationSummaryRefPayload:
    has_response_quality = run.response_quality is not None
    has_trajectory_evaluation = run.trajectory_evaluation is not None
    trajectory_evaluation = run.trajectory_evaluation or {}
    response_quality = run.response_quality or {}

    if run.ended_at is None or (not has_response_quality and not has_trajectory_evaluation):
        status = "not_available"
    elif has_response_quality and has_trajectory_evaluation:
        status = "complete"
    else:
        status = "partial"

    trajectory_violation_count = None
    if has_trajectory_evaluation:
        trajectory_violation_count = len(trajectory_evaluation.get("violations") or [])

    return EvaluationSummaryRefPayload(
        status=status,
        trace_id=run.trace_id,
        has_response_quality=has_response_quality,
        response_quality_overall_score=(
            response_quality.get("overall_score") if has_response_quality else None
        ),
        has_trajectory_evaluation=has_trajectory_evaluation,
        trajectory_score=(
            trajectory_evaluation.get("score") if has_trajectory_evaluation else None
        ),
        trajectory_violation_count=trajectory_violation_count,
    )


def build_ticket_claim_projection(
    *,
    ticket: Ticket,
    run: TicketRun | None,
) -> TicketClaimProjectionPayload:
    projection = build_claim_projection(
        lease_owner=ticket.lease_owner,
        lease_expires_at=ticket.lease_expires_at,
        current_run_id=ticket.current_run_id,
        run_id=run.run_id if run is not None else None,
        run_started_at=run.started_at if run is not None else None,
    )
    return TicketClaimProjectionPayload(**projection)


def _percentile(values: list[float | int | None], percentile: int) -> float | None:
    numeric = sorted(float(value) for value in values if value is not None)
    if not numeric:
        return None
    if len(numeric) == 1:
        return round(numeric[0], 3)
    index = (len(numeric) - 1) * (percentile / 100)
    lower = int(index)
    upper = min(lower + 1, len(numeric) - 1)
    fraction = index - lower
    return round(
        numeric[lower] + (numeric[upper] - numeric[lower]) * fraction,
        3,
    )


def _average(values: list[float | int | None]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return round(mean(numeric), 3)


def _get_number(payload: dict[str, Any] | None, key: str) -> float | int | None:
    if not payload:
        return None
    return payload.get(key)
