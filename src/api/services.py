from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core_schema import (
    EntityIdPrefix,
    HumanReviewAction,
    MemorySourceStage,
    RunFinalAction,
    RunStatus,
    RunTriggerType,
    TicketBusinessStatus,
    TraceEventStatus,
    TraceEventType,
    generate_prefixed_id,
    to_api_timestamp,
    utc_now,
)
from src.customer_memory import CustomerMemoryService
from src.db.models import AppMetadata, DraftArtifact, Ticket, TicketRun, TraceEvent
from src.graph import Workflow
from src.message_log import IngestEmailPayload, MessageLogService
from src.observability import (
    ResponseQualityJudge,
    TraceRecorder,
    build_trajectory_evaluation,
)
from src.state import build_ticket_run_state
from src.ticket_state_machine import TicketStateService
from src.tools.service_container import ServiceContainer, get_service_container
from src.tools.types import TicketStoreProtocol


@dataclass(frozen=True)
class RunExecutionResult:
    ticket: Ticket
    run: TicketRun


class DuplicateRequestError(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(f"Duplicate request for idempotency key `{key}`.")
        self.key = key


class TicketNotFoundError(Exception):
    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"Ticket `{ticket_id}` does not exist.")
        self.ticket_id = ticket_id


class CustomerNotFoundError(Exception):
    def __init__(self, customer_id: str) -> None:
        super().__init__(f"Customer `{customer_id}` does not exist.")
        self.customer_id = customer_id


class RunNotFoundError(Exception):
    def __init__(self, *, ticket_id: str, run_id: str) -> None:
        super().__init__(f"Run `{run_id}` does not exist for ticket `{ticket_id}`.")
        self.ticket_id = ticket_id
        self.run_id = run_id


class RunExecutionFailedError(Exception):
    def __init__(self, *, ticket: Ticket, run: TicketRun) -> None:
        super().__init__(f"Run `{run.run_id}` failed for ticket `{ticket.ticket_id}`.")
        self.ticket = ticket
        self.run = run


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


class TicketApiService:
    def __init__(
        self,
        store: TicketStoreProtocol,
        container: ServiceContainer | None = None,
    ) -> None:
        self._store = store
        self._container = container or get_service_container()

    def ingest_email(
        self,
        *,
        payload: IngestEmailPayload,
        idempotency_key: str | None,
    ) -> tuple[Ticket, bool]:
        expected_key = (
            f"ingest:{payload.source_channel}:{payload.source_thread_id}:{payload.source_message_id}"
        )
        key_to_use = idempotency_key or expected_key

        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            idempotency = IdempotencyService(session)
            if idempotency_key is not None:
                idempotency.ensure_available(key_to_use)

            service = MessageLogService(session, repositories=repositories)
            result = service.ingest_inbound_email(payload)
            session.flush()
            idempotency.record(
                key_to_use,
                {
                    "ticket_id": result.ticket.ticket_id,
                    "created": result.created_ticket,
                    "source_message_id": payload.source_message_id,
                },
            )
            return result.ticket, result.created_ticket

    def get_ticket_snapshot(
        self,
        ticket_id: str,
    ) -> tuple[Ticket, TicketRun | None, DraftArtifact | None]:
        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            latest_run = _select_latest_run(repositories.ticket_runs.list_by_ticket(ticket_id))
            latest_draft = _select_latest_draft(
                repositories.draft_artifacts.list_by_ticket(ticket_id)
            )
            return ticket, latest_run, latest_draft

    def run_ticket(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        trigger_type: str,
        force_retry: bool,
        actor_id: str | None,
        request_id: str | None,
        idempotency_key: str | None,
    ) -> RunExecutionResult:
        key_to_use = idempotency_key or (
            f"run:{ticket_id}:{ticket_version}:{trigger_type}:{force_retry}:{request_id or ''}"
        )
        with self._store.session_scope() as session:
            idempotency = IdempotencyService(session)
            if idempotency_key is not None:
                idempotency.ensure_available(key_to_use)

            repositories = self._store.repositories(session)
            state_service = TicketStateService(session, repositories=repositories)
            runner = TicketRunner(
                session=session,
                store=self._store,
                repositories=repositories,
                container=self._container,
            )
            result = runner.execute(
                ticket_id=ticket_id,
                ticket_version=ticket_version,
                trigger_type=trigger_type,
                force_retry=force_retry,
                actor_id=actor_id,
                request_id=request_id,
                state_service=state_service,
            )
            if result.run.status == RunStatus.FAILED.value:
                session.flush()
                session.commit()
                raise RunExecutionFailedError(ticket=result.ticket, run=result.run)
            session.flush()
            idempotency.record(
                key_to_use,
                {
                    "ticket_id": result.ticket.ticket_id,
                    "run_id": result.run.run_id,
                    "trace_id": result.run.trace_id,
                },
            )
            return result

    def approve_ticket(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        draft_id: str,
        comment: str | None,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[Ticket, str]:
        return self._apply_manual_action(
            ticket_id=ticket_id,
            ticket_version=ticket_version,
            action=HumanReviewAction.APPROVE,
            draft_id=draft_id,
            comment=comment,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

    def edit_and_approve_ticket(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        draft_id: str,
        comment: str | None,
        edited_content_text: str,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[Ticket, str]:
        key_to_use = idempotency_key or (
            f"manual:{ticket_id}:{HumanReviewAction.EDIT_AND_APPROVE.value}:"
            f"{ticket_version}:{draft_id}:{actor_id}"
        )
        with self._store.session_scope() as session:
            idempotency = IdempotencyService(session)
            if idempotency_key is not None:
                idempotency.ensure_available(key_to_use)
            repositories = self._store.repositories(session)
            state_service = TicketStateService(session, repositories=repositories)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            run = self._create_human_action_run(
                session=session,
                repositories=repositories,
                ticket=ticket,
                actor_id=actor_id,
                state_service=state_service,
            )
            updated, review = state_service.apply_manual_review_action(
                ticket_id=ticket_id,
                action=HumanReviewAction.EDIT_AND_APPROVE,
                reviewer_id=actor_id,
                ticket_version_at_review=ticket_version,
                draft_id=draft_id,
                comment=comment,
                edited_content_text=edited_content_text,
                run_id=run.run_id,
            )
            run.status = RunStatus.SUCCEEDED.value
            run.final_action = RunFinalAction.HANDOFF_TO_HUMAN.value
            run.ended_at = utc_now()
            run.latency_metrics = {
                "end_to_end_ms": _duration_ms(run.started_at, run.ended_at)
            }
            session.flush()
            idempotency.record(
                key_to_use,
                {
                    "ticket_id": updated.ticket_id,
                    "review_id": review.review_id,
                    "run_id": run.run_id,
                    "trace_id": run.trace_id,
                    "action": HumanReviewAction.EDIT_AND_APPROVE.value,
                },
            )
            return updated, review.review_id

    def rewrite_ticket(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        draft_id: str,
        comment: str | None,
        rewrite_reasons: list[str],
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[Ticket, str]:
        return self._apply_manual_action(
            ticket_id=ticket_id,
            ticket_version=ticket_version,
            action=HumanReviewAction.REJECT_FOR_REWRITE,
            draft_id=draft_id,
            comment=comment,
            rewrite_reasons=rewrite_reasons,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

    def escalate_ticket(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        comment: str | None,
        target_queue: str,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[Ticket, str]:
        return self._apply_manual_action(
            ticket_id=ticket_id,
            ticket_version=ticket_version,
            action=HumanReviewAction.ESCALATE,
            comment=comment,
            target_queue=target_queue,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

    def close_ticket(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        reason: str,
        actor_id: str,
        idempotency_key: str | None = None,
    ) -> Ticket:
        key_to_use = idempotency_key or (
            f"manual:{ticket_id}:close:{ticket_version}:{reason}:{actor_id}"
        )
        with self._store.session_scope() as session:
            idempotency = IdempotencyService(session)
            if idempotency_key is not None:
                idempotency.ensure_available(key_to_use)
            repositories = self._store.repositories(session)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            state_service = TicketStateService(session, repositories=repositories)
            updated = state_service.apply_close_action(
                ticket_id=ticket_id,
                ticket_version=ticket_version,
                reason=reason,
            )
            run = self._create_system_action_run(
                session=session,
                repositories=repositories,
                ticket=updated,
                trigger_type=RunTriggerType.HUMAN_ACTION,
                actor_id=actor_id,
                state_service=state_service,
            )
            CustomerMemoryService(session, repositories=repositories).apply_stage_updates(
                ticket=updated,
                run=run,
                stage=MemorySourceStage.CLOSE_TICKET,
                review_comment=reason,
            )
            run.status = RunStatus.SUCCEEDED.value
            run.final_action = RunFinalAction.CLOSE_TICKET.value
            run.ended_at = utc_now()
            run.latency_metrics = {
                "end_to_end_ms": _duration_ms(run.started_at, run.ended_at)
            }
            session.flush()
            idempotency.record(
                key_to_use,
                {
                    "ticket_id": updated.ticket_id,
                    "run_id": run.run_id,
                    "trace_id": run.trace_id,
                    "action": "close",
                },
            )
            return updated

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
                },
                "response_quality": {
                    "avg_overall_score": _average(response_scores),
                },
                "trajectory_evaluation": {
                    "avg_score": _average(trajectory_scores),
                },
            }

    def _apply_manual_action(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        action: HumanReviewAction,
        actor_id: str,
        draft_id: str | None = None,
        comment: str | None = None,
        rewrite_reasons: list[str] | None = None,
        target_queue: str | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[Ticket, str]:
        key_parts = [
            "manual",
            ticket_id,
            action.value,
            str(ticket_version),
            actor_id,
            draft_id or "",
            comment or "",
            ",".join(rewrite_reasons or []),
            target_queue or "",
        ]
        key_to_use = idempotency_key or ":".join(key_parts)
        with self._store.session_scope() as session:
            idempotency = IdempotencyService(session)
            if idempotency_key is not None:
                idempotency.ensure_available(key_to_use)
            repositories = self._store.repositories(session)
            ticket = repositories.tickets.get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            state_service = TicketStateService(session, repositories=repositories)
            updated, review = state_service.apply_manual_review_action(
                ticket_id=ticket_id,
                action=action,
                reviewer_id=actor_id,
                ticket_version_at_review=ticket_version,
                draft_id=draft_id,
                comment=comment,
                rewrite_reasons=rewrite_reasons,
                target_queue=target_queue,
            )
            run = self._create_system_action_run(
                session=session,
                repositories=repositories,
                ticket=updated,
                trigger_type=RunTriggerType.HUMAN_ACTION,
                actor_id=actor_id,
                state_service=state_service,
            )
            if action is HumanReviewAction.ESCALATE:
                CustomerMemoryService(session, repositories=repositories).apply_stage_updates(
                    ticket=updated,
                    run=run,
                    stage=MemorySourceStage.ESCALATE_TO_HUMAN,
                    review_comment=comment,
                    target_queue=target_queue,
                )
            run.status = RunStatus.SUCCEEDED.value
            run.final_action = self._manual_action_final_action(action, updated)
            run.ended_at = utc_now()
            run.latency_metrics = {
                "end_to_end_ms": _duration_ms(run.started_at, run.ended_at)
            }
            session.flush()
            idempotency.record(
                key_to_use,
                {
                    "ticket_id": updated.ticket_id,
                    "review_id": review.review_id,
                    "run_id": run.run_id,
                    "trace_id": run.trace_id,
                    "action": action.value,
                },
            )
            return updated, review.review_id

    def _create_human_action_run(
        self,
        *,
        session: Session,
        repositories,
        ticket: Ticket,
        actor_id: str,
        state_service: TicketStateService,
    ) -> TicketRun:
        run = TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type=RunTriggerType.HUMAN_ACTION.value,
            triggered_by=actor_id,
            status=RunStatus.RUNNING.value,
            started_at=utc_now(),
            attempt_index=state_service.get_next_run_attempt_index(ticket.ticket_id),
        )
        repositories.ticket_runs.add(run)
        session.flush()
        return run

    def _create_system_action_run(
        self,
        *,
        session: Session,
        repositories,
        ticket: Ticket,
        trigger_type: RunTriggerType,
        actor_id: str,
        state_service: TicketStateService,
    ) -> TicketRun:
        run = TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type=trigger_type.value,
            triggered_by=actor_id,
            status=RunStatus.RUNNING.value,
            started_at=utc_now(),
            attempt_index=state_service.get_next_run_attempt_index(ticket.ticket_id),
        )
        repositories.ticket_runs.add(run)
        session.flush()
        return run

    def _manual_action_final_action(
        self,
        action: HumanReviewAction,
        ticket: Ticket,
    ) -> str:
        if action is HumanReviewAction.ESCALATE:
            return RunFinalAction.HANDOFF_TO_HUMAN.value
        if ticket.business_status == TicketBusinessStatus.CLOSED.value:
            return RunFinalAction.CLOSE_TICKET.value
        return RunFinalAction.NO_OP.value


class TicketRunner:
    def __init__(
        self,
        *,
        session: Session,
        store: TicketStoreProtocol,
        repositories,
        container: ServiceContainer,
    ) -> None:
        self._session = session
        self._store = store
        self._repositories = repositories
        self._container = container
        self._message_log = MessageLogService(session, repositories=repositories)
        self._memory_service = CustomerMemoryService(session, repositories=repositories)
        self._trace_recorder = TraceRecorder(repositories=repositories)
        self._quality_judge = ResponseQualityJudge()

    def execute(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        trigger_type: str,
        force_retry: bool,
        actor_id: str | None,
        request_id: str | None,
        state_service: TicketStateService,
    ) -> RunExecutionResult:
        ticket = self._repositories.tickets.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)

        normalized_trigger = RunTriggerType(trigger_type)
        worker_id = request_id or actor_id or f"api:{ticket_id}"

        if TicketBusinessStatus(ticket.business_status) is TicketBusinessStatus.FAILED:
            ticket = state_service.requeue_failed_ticket(
                ticket_id,
                expected_version=ticket_version,
                run_id=None,
                force_retry=force_retry,
            )
            ticket_version = ticket.version

        run = TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type=normalized_trigger.value,
            triggered_by=actor_id,
            status=RunStatus.RUNNING.value,
            started_at=utc_now(),
            attempt_index=state_service.get_next_run_attempt_index(ticket.ticket_id),
        )
        self._repositories.ticket_runs.add(run)
        self._session.flush()
        self._trace_recorder.start_run(
            ticket=ticket,
            run=run,
            inputs={
                "ticket_id": ticket.ticket_id,
                "ticket_version": ticket_version,
                "trigger_type": normalized_trigger.value,
                "force_retry": force_retry,
            },
            metadata={"triggered_by": actor_id, "worker_id": worker_id},
        )

        claimed = state_service.claim_ticket(
            ticket.ticket_id,
            worker_id=worker_id,
            run_id=run.run_id,
            expected_version=ticket_version,
        )
        running = state_service.start_run(
            ticket.ticket_id,
            worker_id=worker_id,
            expected_version=claimed.version,
        )

        try:
            workflow = Workflow(
                service_container=self._container,
                session=self._session,
                repositories=self._repositories,
                state_service=state_service,
                message_log=self._message_log,
                run=run,
                worker_id=worker_id,
                trace_recorder=self._trace_recorder,
            )
            initial_state = build_ticket_run_state(
                ticket_id=running.ticket_id,
                customer_id=running.customer_id,
                business_status=running.business_status,
                processing_status=running.processing_status,
                ticket_version=running.version,
                priority=running.priority,
                trace_id=run.trace_id,
                run_id=run.run_id,
                trigger_type=normalized_trigger.value,
                triggered_by=actor_id,
            )
            for _ in workflow.app.stream(initial_state):
                pass
            finalized_ticket = self._repositories.tickets.get(running.ticket_id)
            if finalized_ticket is None:
                raise TicketNotFoundError(running.ticket_id)
        except Exception as exc:
            latest_ticket = self._repositories.tickets.get(running.ticket_id)
            failed_ticket = state_service.fail_run(
                running.ticket_id,
                worker_id=worker_id,
                error_code="run_execution_failed",
                error_message=str(exc),
                expected_version=latest_ticket.version if latest_ticket is not None else running.version,
            )
            run.status = RunStatus.FAILED.value
            run.error_code = failed_ticket.last_error_code
            run.error_message = failed_ticket.last_error_message
            run.ended_at = utc_now()
            run.final_node = "run_ticket"
            run.latency_metrics = self._trace_recorder.build_latency_metrics(run=run)
            run.resource_metrics = self._trace_recorder.build_resource_metrics(run=run)
            run.response_quality = None
            run.trajectory_evaluation = build_trajectory_evaluation(
                ticket=failed_ticket,
                final_action=run.final_action,
                events=self._trace_recorder.list_run_events(run.run_id),
            )
            self._trace_recorder.record_event(
                run=run,
                ticket=failed_ticket,
                event_type=TraceEventType.NODE.value,
                event_name="run_ticket",
                node_name="run_ticket",
                start_time=run.started_at,
                end_time=run.ended_at,
                status=TraceEventStatus.FAILED.value,
                metadata={"error_code": run.error_code, "error_message": run.error_message},
            )
            self._trace_recorder.finalize_run(run=run, ticket=failed_ticket, error=str(exc))
            return RunExecutionResult(ticket=failed_ticket, run=run)

        run.status = RunStatus.SUCCEEDED.value
        run.ended_at = utc_now()
        run.final_action = self._final_action_for_ticket(finalized_ticket)
        run.final_node = "run_ticket"
        self._trace_recorder.record_event(
            run=run,
            ticket=finalized_ticket,
            event_type=TraceEventType.NODE.value,
            event_name="run_ticket",
            node_name="run_ticket",
            start_time=run.started_at,
            end_time=run.ended_at,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata={"final_action": run.final_action},
        )
        run.latency_metrics = self._trace_recorder.build_latency_metrics(run=run)
        run.resource_metrics = self._trace_recorder.build_resource_metrics(run=run)
        run.response_quality = self._build_response_quality(finalized_ticket)
        run.trajectory_evaluation = self._build_trajectory_evaluation(finalized_ticket)
        self._trace_recorder.finalize_run(run=run, ticket=finalized_ticket)

        return RunExecutionResult(ticket=finalized_ticket, run=run)

    def _final_action_for_ticket(self, ticket: Ticket) -> str:
        status = TicketBusinessStatus(ticket.business_status)
        if status is TicketBusinessStatus.AWAITING_CUSTOMER_INPUT:
            return RunFinalAction.REQUEST_CLARIFICATION.value
        if status is TicketBusinessStatus.AWAITING_HUMAN_REVIEW:
            return RunFinalAction.HANDOFF_TO_HUMAN.value
        if ticket.primary_route == "unrelated":
            return RunFinalAction.SKIP_UNRELATED.value
        return RunFinalAction.CREATE_DRAFT.value

    def _build_response_quality(self, ticket: Ticket) -> dict[str, Any]:
        latest_draft = _select_latest_draft(
            self._repositories.draft_artifacts.list_by_ticket(ticket.ticket_id)
        )
        policy_summary = ""
        if ticket.primary_route and hasattr(self._container.policy_provider, "get_policy"):
            policy_summary = self._container.policy_provider.get_policy(ticket.primary_route)
        return self._quality_judge.evaluate(
            email_subject=ticket.subject,
            email_body=ticket.latest_message_excerpt,
            draft_text=latest_draft.content_text if latest_draft is not None else None,
            evidence_summary=(
                latest_draft.source_evidence_summary if latest_draft is not None else None
            ),
            policy_summary=policy_summary,
            primary_route=ticket.primary_route,
            final_action=self._final_action_for_ticket(ticket),
        )

    def _build_trajectory_evaluation(self, ticket: Ticket) -> dict[str, Any]:
        latest_run = _select_latest_run(self._repositories.ticket_runs.list_by_ticket(ticket.ticket_id))
        if latest_run is None:
            return {
                "score": 0.0,
                "expected_route": [],
                "actual_route": [],
                "violations": [],
            }
        return build_trajectory_evaluation(
            ticket=ticket,
            final_action=latest_run.final_action,
            events=self._trace_recorder.list_run_events(latest_run.run_id),
        )


def _select_latest_run(runs: Iterable[TicketRun]) -> TicketRun | None:
    ordered = sorted(
        runs,
        key=lambda item: (item.started_at, item.created_at, item.run_id),
        reverse=True,
    )
    return ordered[0] if ordered else None


def _select_latest_draft(drafts: Iterable[DraftArtifact]) -> DraftArtifact | None:
    ordered = sorted(
        drafts,
        key=lambda item: (item.version_index, item.created_at, item.draft_id),
        reverse=True,
    )
    return ordered[0] if ordered else None


def _duration_ms(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)


def _build_draft_message_payload(
    *,
    ticket: Ticket,
    run: TicketRun,
    draft: DraftArtifact,
    subject: str | None,
    body_text: str,
    message_type: str,
):
    from src.message_log import DraftMessagePayload

    return DraftMessagePayload(
        ticket_id=ticket.ticket_id,
        run_id=run.run_id,
        draft_id=draft.draft_id,
        source_thread_id=ticket.source_thread_id,
        source_message_id=f"{run.run_id}:{draft.version_index}:{message_type}",
        gmail_thread_id=ticket.gmail_thread_id,
        message_type=message_type,
        sender_email="support@example.com",
        recipient_emails=[ticket.customer_email],
        subject=subject,
        body_text=body_text,
        body_html=None,
        message_timestamp=utc_now(),
        reply_to_source_message_id=ticket.source_message_id,
    )


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
