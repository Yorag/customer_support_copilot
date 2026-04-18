from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select

from src.api.service_errors import CustomerNotFoundError, RunNotFoundError, TicketNotFoundError
from src.contracts.core import RunTriggerType, to_api_timestamp
from src.db.models import DraftArtifact, Ticket, TicketRun, TraceEvent

from .base import TicketApiServiceBase
from .common import (
    EvaluationSummaryRefPayload,
    TicketClaimProjectionPayload,
    _average,
    _get_number,
    _percentile,
    _select_latest_draft,
    _select_latest_run,
    _select_latest_snapshot_run,
    build_evaluation_summary_ref,
    build_ticket_claim_projection,
)


@dataclass(frozen=True)
class TicketListItemPayload:
    ticket: Ticket
    latest_run: TicketRun | None
    evaluation_summary_ref: EvaluationSummaryRefPayload | None
    latest_draft: DraftArtifact | None


@dataclass(frozen=True)
class TicketListPayload:
    items: list[TicketListItemPayload]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class TicketRunHistoryItemPayload:
    run: TicketRun
    evaluation_summary_ref: EvaluationSummaryRefPayload


@dataclass(frozen=True)
class TicketRunsPayload:
    ticket_id: str
    items: list[TicketRunHistoryItemPayload]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class TicketDraftsPayload:
    ticket_id: str
    items: list[DraftArtifact]


@dataclass(frozen=True)
class TicketMessagePayload:
    ticket_message_id: str
    run_id: str | None
    draft_id: str | None
    source_message_id: str
    direction: str
    message_type: str
    sender_email: str | None
    recipient_emails: list[str]
    subject: str | None
    body_text: str | None
    reply_to_source_message_id: str | None
    customer_visible: bool
    message_timestamp: datetime
    message_metadata: dict[str, Any] | None


class TicketQueryServiceMixin:
    def list_tickets(
        self,
        *,
        page: int,
        page_size: int,
        business_status: str | None = None,
        processing_status: str | None = None,
        primary_route: str | None = None,
        has_draft: bool | None = None,
        awaiting_review: bool | None = None,
        query: str | None = None,
    ) -> TicketListPayload:
        with self._store.session_scope() as session:
            filters = [Ticket.is_active.is_(True)]

            if business_status is not None:
                filters.append(Ticket.business_status == business_status)
            if processing_status is not None:
                filters.append(Ticket.processing_status == processing_status)
            if primary_route is not None:
                filters.append(Ticket.primary_route == primary_route)
            if has_draft is not None:
                draft_exists = (
                    select(DraftArtifact.draft_id)
                    .where(DraftArtifact.ticket_id == Ticket.ticket_id)
                    .exists()
                )
                filters.append(draft_exists if has_draft else ~draft_exists)
            if awaiting_review is not None:
                if awaiting_review:
                    filters.append(Ticket.business_status == "awaiting_human_review")
                else:
                    filters.append(Ticket.business_status != "awaiting_human_review")
            if query is not None:
                search_term = f"%{query.strip()}%"
                filters.append(
                    or_(
                        Ticket.ticket_id.ilike(search_term),
                        Ticket.subject.ilike(search_term),
                        Ticket.customer_email_raw.ilike(search_term),
                    )
                )

            total = session.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0
            statement = (
                select(Ticket)
                .where(*filters)
                .order_by(Ticket.updated_at.desc(), Ticket.ticket_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            tickets = list(session.scalars(statement))
            if not tickets:
                return TicketListPayload(items=[], page=page, page_size=page_size, total=total)

            ticket_ids = [ticket.ticket_id for ticket in tickets]
            runs = list(
                session.scalars(select(TicketRun).where(TicketRun.ticket_id.in_(ticket_ids)))
            )
            drafts = list(
                session.scalars(
                    select(DraftArtifact).where(DraftArtifact.ticket_id.in_(ticket_ids))
                )
            )

            runs_by_ticket: dict[str, list[TicketRun]] = {ticket_id: [] for ticket_id in ticket_ids}
            for run in runs:
                runs_by_ticket.setdefault(run.ticket_id, []).append(run)

            drafts_by_ticket: dict[str, list[DraftArtifact]] = {
                ticket_id: [] for ticket_id in ticket_ids
            }
            for draft in drafts:
                drafts_by_ticket.setdefault(draft.ticket_id, []).append(draft)

            items = []
            for ticket in tickets:
                latest_run = _select_latest_snapshot_run(runs_by_ticket.get(ticket.ticket_id, []))
                latest_draft = _select_latest_draft(drafts_by_ticket.get(ticket.ticket_id, []))
                items.append(
                    TicketListItemPayload(
                        ticket=ticket,
                        latest_run=latest_run,
                        evaluation_summary_ref=(
                            build_evaluation_summary_ref(latest_run)
                            if latest_run is not None
                            else None
                        ),
                        latest_draft=latest_draft,
                    )
                )

            return TicketListPayload(
                items=items,
                page=page,
                page_size=page_size,
                total=total,
            )

    def get_ticket_runs(
        self,
        ticket_id: str,
        *,
        page: int,
        page_size: int,
    ) -> TicketRunsPayload:
        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            runs = repositories.ticket_runs.list_by_ticket(ticket_id)
            ordered_runs = sorted(
                runs,
                key=lambda item: (item.created_at, item.run_id),
                reverse=True,
            )
            total = len(ordered_runs)
            selected_runs = ordered_runs[(page - 1) * page_size : page * page_size]
            items = [
                TicketRunHistoryItemPayload(
                    run=run,
                    evaluation_summary_ref=build_evaluation_summary_ref(run),
                )
                for run in selected_runs
            ]
            return TicketRunsPayload(
                ticket_id=ticket_id,
                items=items,
                page=page,
                page_size=page_size,
                total=total,
            )

    def get_ticket_drafts(
        self,
        ticket_id: str,
    ) -> TicketDraftsPayload:
        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            drafts = repositories.draft_artifacts.list_by_ticket(ticket_id)
            ordered_drafts = sorted(
                drafts,
                key=lambda item: (item.version_index, item.created_at, item.draft_id),
            )
            return TicketDraftsPayload(ticket_id=ticket_id, items=ordered_drafts)

    def get_ticket_snapshot(
        self,
        ticket_id: str,
    ) -> tuple[
        Ticket,
        TicketRun | None,
        TicketClaimProjectionPayload,
        EvaluationSummaryRefPayload | None,
        DraftArtifact | None,
        list[TicketMessagePayload],
    ]:
        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            current_run = (
                repositories.ticket_runs.get(ticket.current_run_id)
                if ticket.current_run_id
                else None
            )
            latest_run = _select_latest_snapshot_run(
                repositories.ticket_runs.list_by_ticket(ticket_id)
            )
            claim_projection = build_ticket_claim_projection(ticket=ticket, run=current_run)
            evaluation_summary_ref = (
                build_evaluation_summary_ref(latest_run) if latest_run is not None else None
            )
            latest_draft = _select_latest_draft(
                repositories.draft_artifacts.list_by_ticket(ticket_id)
            )
            messages = [
                TicketMessagePayload(
                    ticket_message_id=item.ticket_message_id,
                    run_id=item.run_id,
                    draft_id=item.draft_id,
                    source_message_id=item.source_message_id,
                    direction=item.direction,
                    message_type=item.message_type,
                    sender_email=item.sender_email,
                    recipient_emails=list(item.recipient_emails or []),
                    subject=item.subject,
                    body_text=item.body_text,
                    reply_to_source_message_id=item.reply_to_source_message_id,
                    customer_visible=item.customer_visible,
                    message_timestamp=item.message_timestamp,
                    message_metadata=item.message_metadata,
                )
                for item in sorted(
                    repositories.ticket_messages.list_by_ticket(ticket_id),
                    key=lambda message: (
                        message.message_timestamp,
                        message.created_at,
                        message.ticket_message_id,
                    ),
                )
            ]
            return (
                ticket,
                latest_run,
                claim_projection,
                evaluation_summary_ref,
                latest_draft,
                messages,
            )

    def get_customer_memory(self, customer_id: str):
        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            profile = repositories.customer_memory_profiles.get(customer_id)
            if profile is None:
                raise CustomerNotFoundError(customer_id)
            return profile

    def get_ticket_trace(
        self,
        ticket_id: str,
        run_id: str | None = None,
    ) -> tuple[Ticket, TicketRun, list[TraceEvent]]:
        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)
            selected_run = (
                repositories.ticket_runs.get(run_id)
                if run_id is not None
                else _select_latest_run(repositories.ticket_runs.list_by_ticket(ticket_id))
            )
            if selected_run is None or selected_run.ticket_id != ticket_id:
                raise RunNotFoundError(ticket_id=ticket_id, run_id=run_id or "")
            events = repositories.trace_events.list_by_run(selected_run.run_id)
            events.sort(key=lambda item: (item.start_time, item.created_at))
            return ticket, selected_run, events

    def get_metrics_summary(
        self,
        *,
        from_time: datetime,
        to_time: datetime,
        route: str | None = None,
    ) -> dict[str, Any]:
        with self._store.session_scope() as session:
            statement = (
                select(TicketRun, Ticket)
                .join(Ticket, Ticket.ticket_id == TicketRun.ticket_id)
                .where(
                    TicketRun.started_at >= from_time,
                    TicketRun.started_at <= to_time,
                    TicketRun.trigger_type != RunTriggerType.HUMAN_ACTION.value,
                )
            )
            if route is not None:
                statement = statement.where(Ticket.primary_route == route)
            rows = session.execute(statement).all()
            runs = [row[0] for row in rows]

            end_to_end_values = [
                _get_number(run.latency_metrics, "end_to_end_ms") for run in runs
            ]
            total_tokens = [
                _get_number(run.resource_metrics, "total_tokens") for run in runs
            ]
            llm_calls = [
                _get_number(run.resource_metrics, "llm_call_count") for run in runs
            ]
            actual_token_calls = [
                _get_number(run.resource_metrics, "actual_token_call_count") for run in runs
            ]
            estimated_token_calls = [
                _get_number(run.resource_metrics, "estimated_token_call_count") for run in runs
            ]
            unavailable_token_calls = [
                _get_number(run.resource_metrics, "unavailable_token_call_count") for run in runs
            ]
            token_coverage_ratios = [
                _get_number(run.resource_metrics, "token_coverage_ratio") for run in runs
            ]
            response_scores = [
                _get_number(run.response_quality, "overall_score") for run in runs
            ]
            trajectory_scores = [
                _get_number(run.trajectory_evaluation, "score") for run in runs
            ]

            return {
                "window": {
                    "from": to_api_timestamp(from_time),
                    "to": to_api_timestamp(to_time),
                },
                "latency": {
                    "p50_ms": _percentile(end_to_end_values, 50),
                    "p95_ms": _percentile(end_to_end_values, 95),
                },
                "resources": {
                    "avg_total_tokens": _average(total_tokens),
                    "avg_llm_call_count": _average(llm_calls),
                    "avg_actual_token_call_count": _average(actual_token_calls),
                    "avg_estimated_token_call_count": _average(estimated_token_calls),
                    "avg_unavailable_token_call_count": _average(unavailable_token_calls),
                    "avg_token_coverage_ratio": _average(token_coverage_ratios),
                },
                "response_quality": {
                    "avg_overall_score": _average(response_scores),
                },
                "trajectory_evaluation": {
                    "avg_score": _average(trajectory_scores),
                },
            }
