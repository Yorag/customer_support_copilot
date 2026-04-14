from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any

from src.contracts.core import (
    EntityIdPrefix,
    TraceEventStatus,
    TraceEventType,
    generate_prefixed_id,
    utc_now,
)
from src.contracts.protocols import TraceExporterProtocol
from src.db.models import Ticket, TicketRun, TraceEvent

from .metrics import (
    duration_ms,
    build_latency_metrics as _build_latency_metrics,
    build_resource_metrics as _build_resource_metrics,
)
from .exporters import LangSmithTraceClient


class TraceRecorder:
    def __init__(
        self,
        *,
        repositories,
        trace_exporter: TraceExporterProtocol | None = None,
        langsmith_client: TraceExporterProtocol | None = None,
    ) -> None:
        self._repositories = repositories
        self._trace_exporter = trace_exporter or langsmith_client or LangSmithTraceClient()
        self._root_run: Any | None = None
        self._child_runs: dict[str, Any] = {}

    def start_run(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._root_run = self._trace_exporter.create_root_run(
            run=run,
            ticket=ticket,
            inputs=inputs,
            metadata=metadata,
        )

    def finalize_run(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        error: str | None = None,
    ) -> None:
        self._trace_exporter.finalize_run(
            root=self._root_run,
            ended_at=run.ended_at or utc_now(),
            outputs={
                "ticket_id": ticket.ticket_id,
                "run_id": run.run_id,
                "trace_id": run.trace_id,
                "status": run.status,
                "final_action": run.final_action,
                "latency_metrics": run.latency_metrics,
                "resource_metrics": run.resource_metrics,
                "response_quality": run.response_quality,
                "trajectory_evaluation": run.trajectory_evaluation,
            },
            error=error,
            extra_metadata={
                "final_node": run.final_node,
                "ticket_business_status": ticket.business_status,
                "ticket_processing_status": ticket.processing_status,
            },
        )
        self._root_run = None
        self._child_runs.clear()

    def record_event(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_type: str,
        event_name: str,
        node_name: str | None,
        start_time: datetime,
        end_time: datetime,
        status: str,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            event_id=event_id or generate_prefixed_id(EntityIdPrefix.TRACE),
            trace_id=run.trace_id,
            run_id=run.run_id,
            ticket_id=ticket.ticket_id,
            event_type=event_type,
            event_name=event_name,
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            latency_ms=duration_ms(start_time, end_time),
            status=status,
            event_metadata=metadata,
        )
        self._repositories.trace_events.add(event)
        child = self._trace_exporter.create_child_run(
            parent=self._root_run,
            event=event,
            inputs=metadata or {},
            outputs=outputs,
        )
        if child is not None:
            self._child_runs[event.event_id] = child
        return event

    @contextmanager
    def node_span(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ):
        started_at = utc_now()
        try:
            yield
        except Exception as exc:
            self.record_event(
                run=run,
                ticket=ticket,
                event_type=TraceEventType.NODE.value,
                event_name=node_name,
                node_name=node_name,
                start_time=started_at,
                end_time=utc_now(),
                status=TraceEventStatus.FAILED.value,
                metadata={**(metadata or {}), "error_message": str(exc)},
            )
            raise
        else:
            self.record_event(
                run=run,
                ticket=ticket,
                event_type=TraceEventType.NODE.value,
                event_name=node_name,
                node_name=node_name,
                start_time=started_at,
                end_time=utc_now(),
                status=TraceEventStatus.SUCCEEDED.value,
                metadata=metadata,
            )

    def record_decision(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_name: str,
        node_name: str,
        metadata: dict[str, Any],
    ) -> TraceEvent:
        now = utc_now()
        return self.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.DECISION.value,
            event_name=event_name,
            node_name=node_name,
            start_time=now,
            end_time=now,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata=metadata,
        )

    def record_tool_call(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_name: str,
        node_name: str,
        tool_name: str,
        input_ref: str,
        output_ref: str,
        start_time: datetime,
        end_time: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> TraceEvent:
        payload = {
            "tool_name": tool_name,
            "input_ref": input_ref,
            "output_ref": output_ref,
            **(metadata or {}),
        }
        return self.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.TOOL_CALL.value,
            event_name=event_name,
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata=payload,
        )

    def record_llm_call(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_name: str,
        node_name: str,
        model: str,
        provider: str,
        start_time: datetime,
        end_time: datetime,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        token_source: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceEvent:
        total_tokens = None
        if prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
        payload = {
            "model": model,
            "provider": provider,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "token_source": token_source,
            **(metadata or {}),
        }
        return self.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.LLM_CALL.value,
            event_name=event_name,
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata=payload,
        )

    def list_run_events(self, run_id: str) -> list[TraceEvent]:
        events = self._repositories.trace_events.list_by_run(run_id)
        events.sort(key=lambda item: (item.start_time, item.created_at, item.event_id))
        return events

    def build_latency_metrics(
        self,
        *,
        run: TicketRun,
        events: list[TraceEvent] | None = None,
    ) -> dict[str, Any]:
        return _build_latency_metrics(
            run=run,
            events=events if events is not None else self.list_run_events(run.run_id),
        )

    def build_resource_metrics(
        self,
        *,
        run: TicketRun | None = None,
        events: list[TraceEvent] | None = None,
    ) -> dict[str, Any]:
        if events is None:
            if run is None:
                raise ValueError("Either run or events must be provided.")
            events = self.list_run_events(run.run_id)
        return _build_resource_metrics(events=events)


__all__ = ["LangSmithTraceClient", "TraceRecorder"]
