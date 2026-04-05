from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from src.api.service_errors import TicketNotFoundError
from src.bootstrap.container import ServiceContainer
from src.contracts.core import (
    EntityIdPrefix,
    LeaseConflictError,
    ResponseStrategy,
    RunFinalAction,
    RunStatus,
    RunTriggerType,
    TicketBusinessStatus,
    TicketProcessingStatus,
    TicketRoute,
    TraceEventStatus,
    TraceEventType,
    assert_expected_version,
    ensure_timezone_aware,
    generate_prefixed_id,
    to_api_timestamp,
    utc_now,
)
from src.db.models import DraftArtifact, Ticket, TicketRun
from src.evaluation import build_trajectory_evaluation
from src.orchestration.checkpointing import build_checkpoint_config
from src.orchestration.state import build_claim_projection, build_ticket_run_state
from src.orchestration.workflow import Workflow
from src.telemetry.trace import TraceRecorder
from src.tickets.message_log import MessageLogService
from src.tickets.state_machine import TicketStateService


@dataclass(frozen=True)
class RunExecutionResult:
    ticket: Ticket
    run: TicketRun


@dataclass(frozen=True)
class RunEnqueueResult:
    ticket: Ticket
    run: TicketRun


class TicketRunner:
    def __init__(
        self,
        *,
        session: Session,
        repositories,
        container: ServiceContainer,
        checkpointer=None,
    ) -> None:
        self._session = session
        self._repositories = repositories
        self._container = container
        self._message_log = MessageLogService(session, repositories=repositories)
        self._trace_recorder = TraceRecorder(repositories=repositories)
        self._quality_judge = container.response_quality_judge
        self._checkpointer = checkpointer

    @property
    def trace_recorder(self) -> TraceRecorder:
        return self._trace_recorder

    def _with_checkpointer(
        self,
        config: dict[str, Any],
        checkpointer: Any,
    ) -> dict[str, Any]:
        return {
            **config,
            "configurable": {
                **config["configurable"],
                "__pregel_checkpointer": checkpointer,
            },
        }

    def enqueue(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        trigger_type: str,
        force_retry: bool,
        actor_id: str | None,
        request_id: str | None,
        state_service: TicketStateService,
    ) -> RunEnqueueResult:
        ticket = self._repositories.tickets.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        assert_expected_version(
            expected=ticket_version,
            actual=ticket.version,
            entity="ticket",
        )

        normalized_trigger = RunTriggerType(trigger_type)
        run = TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type=normalized_trigger.value,
            triggered_by=actor_id,
            status=RunStatus.QUEUED.value,
            started_at=None,
            attempt_index=state_service.get_next_run_attempt_index(ticket.ticket_id),
        )
        self._repositories.ticket_runs.add(run)
        self._session.flush()
        queued_ticket = state_service.enqueue_ticket_run(
            ticket.ticket_id,
            run_id=run.run_id,
            expected_version=ticket_version,
            force_retry=force_retry,
        )
        return RunEnqueueResult(ticket=queued_ticket, run=run)

    def start_trace_for_worker_run(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        trigger_type: str,
        actor_id: str | None,
        force_retry: bool,
        worker_id: str,
    ) -> None:
        self._trace_recorder.start_run(
            ticket=ticket,
            run=run,
            inputs={
                "ticket_id": ticket.ticket_id,
                "ticket_version": ticket.version,
                "trigger_type": trigger_type,
                "force_retry": force_retry,
            },
            metadata={"triggered_by": actor_id, "worker_id": worker_id},
        )

    def execute_claimed_run(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        actor_id: str | None,
        worker_id: str,
        state_service: TicketStateService,
        restore_mode: str,
        renew_interval_seconds: int = 60,
    ) -> RunExecutionResult:
        normalized_trigger = RunTriggerType(run.trigger_type)
        workflow = None
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
                checkpointer=self._checkpointer,
            )
            workflow_config = build_checkpoint_config(
                ticket_id=ticket.ticket_id,
                run_id=run.run_id,
            )
            checkpoint_context = self._prepare_checkpoint_context(
                workflow=workflow,
                workflow_config=workflow_config,
                ticket=ticket,
                run=run,
                worker_id=worker_id,
                default_restore_mode=restore_mode,
            )
            stream_input = (
                None
                if checkpoint_context["restore_mode"] == "resume"
                else build_ticket_run_state(
                    ticket_id=ticket.ticket_id,
                    customer_id=ticket.customer_id,
                    business_status=ticket.business_status,
                    processing_status=ticket.processing_status,
                    ticket_version=ticket.version,
                    priority=ticket.priority,
                    trace_id=run.trace_id,
                    run_id=run.run_id,
                    trigger_type=normalized_trigger.value,
                    triggered_by=actor_id,
                    **build_claim_projection(
                        lease_owner=ticket.lease_owner,
                        lease_expires_at=ticket.lease_expires_at,
                        current_run_id=ticket.current_run_id,
                        run_id=run.run_id,
                        run_started_at=run.started_at,
                    ),
                )
            )
            last_lease_renewed_at = utc_now()
            for _ in workflow.app.stream(stream_input, config=checkpoint_context["stream_config"]):
                current_ticket = self._repositories.tickets.get(ticket.ticket_id)
                if current_ticket is None:
                    raise TicketNotFoundError(ticket.ticket_id)
                self._assert_worker_still_owns_run(
                    ticket=current_ticket,
                    run=run,
                    worker_id=worker_id,
                )
                now = utc_now()
                elapsed_seconds = (now - last_lease_renewed_at).total_seconds()
                if elapsed_seconds >= renew_interval_seconds:
                    renewed = state_service.renew_lease(
                        current_ticket.ticket_id,
                        worker_id=worker_id,
                        run_id=run.run_id,
                        expected_version=current_ticket.version,
                        now=now,
                    )
                    self._trace_recorder.record_event(
                        run=run,
                        ticket=renewed,
                        event_type=TraceEventType.WORKER.value,
                        event_name="worker_renew_lease",
                        node_name="ticket_worker",
                        start_time=now,
                        end_time=now,
                        status=TraceEventStatus.SUCCEEDED.value,
                        metadata={
                            "ticket_id": renewed.ticket_id,
                            "run_id": run.run_id,
                            "worker_id": worker_id,
                            "lease_owner": renewed.lease_owner,
                            "lease_expires_at": to_api_timestamp(renewed.lease_expires_at),
                        },
                    )
                    last_lease_renewed_at = now
            finalized_ticket = self._repositories.tickets.get(ticket.ticket_id)
            if finalized_ticket is None:
                raise TicketNotFoundError(ticket.ticket_id)
        except Exception as exc:
            latest_ticket = self._repositories.tickets.get(ticket.ticket_id)
            if latest_ticket is None:
                raise
            failed_ticket = self._handle_run_failure(
                ticket=latest_ticket,
                run=run,
                worker_id=worker_id,
                state_service=state_service,
                error_message=str(exc),
            )
            return RunExecutionResult(ticket=failed_ticket, run=run)
        finally:
            if (
                workflow is not None
                and hasattr(workflow, "checkpointer")
                and hasattr(workflow.checkpointer, "__exit__")
            ):
                workflow.checkpointer.__exit__(None, None, None)

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
        run.response_quality = self._build_response_quality(run=run, ticket=finalized_ticket)
        run.trajectory_evaluation = self._build_trajectory_evaluation(finalized_ticket)
        self._session.flush()
        cached_events = self._trace_recorder.list_run_events(run.run_id)
        run.latency_metrics = self._trace_recorder.build_latency_metrics(run=run, events=cached_events)
        run.resource_metrics = self._trace_recorder.build_resource_metrics(events=cached_events)
        self._trace_recorder.finalize_run(run=run, ticket=finalized_ticket)

        return RunExecutionResult(ticket=finalized_ticket, run=run)

    def _handle_run_failure(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        worker_id: str,
        state_service: TicketStateService,
        error_message: str,
    ) -> Ticket:
        run.ended_at = utc_now()
        run.final_node = "run_ticket"
        try:
            failed_ticket = state_service.fail_run(
                ticket.ticket_id,
                worker_id=worker_id,
                run_id=run.run_id,
                error_code="run_execution_failed",
                error_message=error_message,
                expected_version=ticket.version,
            )
            run.status = RunStatus.FAILED.value
            run.error_code = failed_ticket.last_error_code
            run.error_message = failed_ticket.last_error_message
        except Exception:
            failed_ticket = self._repositories.tickets.get(ticket.ticket_id) or ticket
            run.status = RunStatus.FAILED.value
            run.error_code = "lease_lost"
            run.error_message = error_message
            now = utc_now()
            self._trace_recorder.record_event(
                run=run,
                ticket=failed_ticket,
                event_type=TraceEventType.WORKER.value,
                event_name="worker_lose_lease",
                node_name="ticket_worker",
                start_time=now,
                end_time=now,
                status=TraceEventStatus.FAILED.value,
                metadata={
                    "ticket_id": failed_ticket.ticket_id,
                    "run_id": run.run_id,
                    "worker_id": worker_id,
                    "lease_owner": failed_ticket.lease_owner,
                    "lease_expires_at": (
                        to_api_timestamp(failed_ticket.lease_expires_at)
                        if failed_ticket.lease_expires_at is not None
                        else None
                    ),
                },
            )

        cached_events = self._trace_recorder.list_run_events(run.run_id)
        run.latency_metrics = self._trace_recorder.build_latency_metrics(run=run, events=cached_events)
        run.resource_metrics = self._trace_recorder.build_resource_metrics(events=cached_events)
        run.response_quality = None
        run.trajectory_evaluation = build_trajectory_evaluation(
            ticket=failed_ticket,
            final_action=run.final_action,
            events=cached_events,
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
        self._trace_recorder.finalize_run(run=run, ticket=failed_ticket, error=error_message)
        return failed_ticket

    def _assert_worker_still_owns_run(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        worker_id: str,
    ) -> None:
        if (
            ticket.current_run_id == run.run_id
            and ticket.processing_status in {
                TicketProcessingStatus.WAITING_EXTERNAL.value,
                TicketProcessingStatus.COMPLETED.value,
            }
        ):
            return
        lease_expires_at = normalize_optional_datetime(ticket.lease_expires_at)
        if (
            ticket.lease_owner != worker_id
            or ticket.current_run_id != run.run_id
            or lease_expires_at is None
            or lease_expires_at <= utc_now()
        ):
            raise LeaseConflictError(
                ticket_id=ticket.ticket_id,
                lease_owner=ticket.lease_owner,
                message=(
                    f"Worker `{worker_id}` lost the lease for run `{run.run_id}` "
                    f"on ticket `{ticket.ticket_id}`."
                ),
            )

    def _prepare_checkpoint_context(
        self,
        *,
        workflow: Workflow,
        workflow_config: dict[str, Any],
        ticket: Ticket,
        run: TicketRun,
        worker_id: str,
        default_restore_mode: str,
    ) -> dict[str, Any]:
        checkpointer = workflow.app.checkpointer
        state_config = self._with_checkpointer(workflow_config, checkpointer)
        state_snapshot = workflow.app.get_state(state_config)
        has_checkpoint = bool(
            state_snapshot.config and state_snapshot.config["configurable"].get("checkpoint_id")
        )
        can_resume = (
            has_checkpoint
            and ticket.current_run_id == run.run_id
            and run.ended_at is None
            and ticket.lease_owner == worker_id
            and ticket.lease_expires_at is not None
            and ticket.lease_expires_at > utc_now()
        )
        restore_mode = "resume" if default_restore_mode == "resume" and can_resume else "fresh"
        last_checkpoint_node = None
        last_checkpoint_at = None
        stream_config = state_config
        if can_resume and state_snapshot.config is not None:
            stream_config = self._with_checkpointer(
                state_snapshot.config,
                checkpointer,
            )
            next_nodes = tuple(state_snapshot.next or ())
            if next_nodes:
                last_checkpoint_node = self._find_last_checkpoint_node(run.run_id, next_nodes[0])
            if state_snapshot.created_at is not None:
                last_checkpoint_at = serialize_checkpoint_timestamp(state_snapshot.created_at)
        checkpoint_metadata = {
            "thread_id": workflow_config["configurable"]["thread_id"],
            "checkpoint_ns": workflow_config["configurable"]["checkpoint_ns"],
            "restore_mode": restore_mode,
            "last_checkpoint_node": last_checkpoint_node,
        }
        run.app_metadata = {"checkpoint": checkpoint_metadata}
        did_resume = restore_mode == "resume"
        if did_resume and state_snapshot.config is not None:
            restored_values = dict(state_snapshot.values or {})
            updated_resume_count = int(restored_values.get("resume_count") or 0) + 1
            checkpoint_state_metadata = {
                "thread_id": workflow_config["configurable"]["thread_id"],
                "checkpoint_ns": workflow_config["configurable"]["checkpoint_ns"],
                "last_checkpoint_node": last_checkpoint_node,
                "last_checkpoint_at": last_checkpoint_at,
            }
            updated_stream_config = workflow.app.update_state(
                stream_config,
                {
                    "resume_count": updated_resume_count,
                    "checkpoint_metadata": checkpoint_state_metadata,
                },
            )
            refreshed_state = workflow.app.get_state(
                self._with_checkpointer(updated_stream_config, checkpointer)
            )
            stream_config = self._with_checkpointer(
                refreshed_state.config,
                checkpointer,
            )
        event_time = utc_now()
        self._trace_recorder.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.CHECKPOINT.value,
            event_name="checkpoint_resume_decision",
            node_name="run_ticket",
            start_time=event_time,
            end_time=event_time,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata={**checkpoint_metadata, "restored": did_resume},
        )
        self._trace_recorder.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.CHECKPOINT.value,
            event_name="checkpoint_restore",
            node_name="run_ticket",
            start_time=event_time,
            end_time=event_time,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata={
                **checkpoint_metadata,
                "restored": did_resume,
                "last_checkpoint_at": last_checkpoint_at,
            },
        )
        return {
            "restore_mode": restore_mode,
            "stream_config": stream_config,
        }

    def _find_last_checkpoint_node(self, run_id: str, next_node: str | None) -> str | None:
        if next_node is None:
            return None
        events = self._trace_recorder.list_run_events(run_id)
        node_events = [
            event
            for event in events
            if event.event_type == TraceEventType.NODE.value
            and event.status == TraceEventStatus.SUCCEEDED.value
            and event.node_name not in {None, "run_ticket"}
        ]
        if not node_events:
            return None
        for event in reversed(node_events):
            if event.node_name != next_node:
                return event.node_name
        return node_events[-1].node_name

    def _final_action_for_ticket(self, ticket: Ticket) -> str:
        status = TicketBusinessStatus(ticket.business_status)
        if status is TicketBusinessStatus.AWAITING_CUSTOMER_INPUT:
            return RunFinalAction.REQUEST_CLARIFICATION.value
        if status is TicketBusinessStatus.AWAITING_HUMAN_REVIEW:
            return RunFinalAction.HANDOFF_TO_HUMAN.value
        if ticket.primary_route == TicketRoute.UNRELATED.value:
            return RunFinalAction.SKIP_UNRELATED.value
        return RunFinalAction.CREATE_DRAFT.value

    def _build_response_quality(self, *, run: TicketRun, ticket: Ticket) -> dict[str, Any] | None:
        latest_draft = select_latest_draft(
            self._repositories.draft_artifacts.list_by_ticket(ticket.ticket_id)
        )
        policy_summary = ""
        if ticket.primary_route and hasattr(self._container.policy_provider, "get_policy"):
            policy_summary = self._container.policy_provider.get_policy(ticket.primary_route)
        evaluation = self._quality_judge.evaluate(
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
        llm_metadata = dict(evaluation.llm_metadata)
        status = llm_metadata.pop("judge_status", "failed")
        error_message = llm_metadata.get("error_message")
        latency_ms = llm_metadata.pop("latency_ms", 0)
        app_metadata = dict(run.app_metadata or {})
        app_metadata["response_quality_status"] = status
        run.app_metadata = app_metadata

        event_status = (
            TraceEventStatus.SUCCEEDED.value
            if status == "succeeded"
            else TraceEventStatus.FAILED.value
        )
        end_time = run.ended_at or utc_now()
        started_at = end_time
        if isinstance(latency_ms, int) and latency_ms > 0:
            started_at = end_time - timedelta(milliseconds=latency_ms)
        self._trace_recorder.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.LLM_CALL.value,
            event_name="response_quality_judge",
            node_name="run_ticket",
            start_time=started_at,
            end_time=end_time,
            status=event_status,
            metadata=llm_metadata,
            outputs=evaluation.response_quality,
        )
        if status != "succeeded" and error_message:
            self._trace_recorder.record_event(
                run=run,
                ticket=ticket,
                event_type=TraceEventType.DECISION.value,
                event_name="response_quality_failed",
                node_name="run_ticket",
                start_time=end_time,
                end_time=end_time,
                status=TraceEventStatus.FAILED.value,
                metadata={
                    "primary_route": ticket.primary_route or TicketRoute.UNRELATED.value,
                    "response_strategy": ticket.response_strategy or ResponseStrategy.ANSWER.value,
                    "needs_clarification": bool(ticket.needs_clarification),
                    "needs_escalation": bool(ticket.needs_escalation),
                    "final_action": self._final_action_for_ticket(ticket),
                    "error_message": error_message,
                },
            )
        return evaluation.response_quality

    def _build_trajectory_evaluation(self, ticket: Ticket) -> dict[str, Any]:
        latest_run = select_latest_run(self._repositories.ticket_runs.list_by_ticket(ticket.ticket_id))
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


def select_latest_run(runs) -> TicketRun | None:
    return _select_latest_by(
        runs,
        key=lambda item: (item.started_at or item.created_at, item.created_at, item.run_id),
    )


def select_latest_draft(drafts) -> DraftArtifact | None:
    return _select_latest_by(
        drafts,
        key=lambda item: (item.version_index, item.created_at, item.draft_id),
    )


def _select_latest_by(items, *, key):
    ordered = sorted(items, key=key, reverse=True)
    return ordered[0] if ordered else None


def normalize_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return ensure_timezone_aware(value)


def serialize_checkpoint_timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        return value
    return to_api_timestamp(value)
