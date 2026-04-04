from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

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


class TicketQueryServiceMixin:
    def get_ticket_snapshot(
        self,
        ticket_id: str,
    ) -> tuple[
        Ticket,
        TicketRun | None,
        TicketClaimProjectionPayload,
        EvaluationSummaryRefPayload | None,
        DraftArtifact | None,
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
            return ticket, latest_run, claim_projection, evaluation_summary_ref, latest_draft

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
