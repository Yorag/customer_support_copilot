from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from langsmith import Client
from langsmith.run_trees import RunTree

from src.config import get_settings
from src.contracts.protocols import TraceExporterProtocol
from src.contracts.core import TraceEventType
from src.db.models import Ticket, TicketRun, TraceEvent


_LANGSMITH_NAMESPACE = UUID("12345678-1234-5678-1234-567812345678")


def _uuid_from_prefixed_id(value: str) -> UUID:
    return uuid5(_LANGSMITH_NAMESPACE, value)


class NoOpTraceExporter:
    def create_root_run(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return None

    def create_child_run(
        self,
        *,
        parent: Any | None,
        event: TraceEvent,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> None:
        return None

    def finalize_run(
        self,
        *,
        root: Any | None,
        ended_at: datetime,
        outputs: dict[str, Any],
        error: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        return None


class LangSmithTraceExporter:
    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = bool(settings.langsmith.tracing_enabled and settings.langsmith.api_key)
        self._project = settings.langsmith.project
        self._client = (
            Client(
                api_key=settings.langsmith.api_key,
                api_url=settings.langsmith.endpoint,
            )
            if self._enabled
            else None
        )

    def create_root_run(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> RunTree | None:
        if self._client is None:
            return None
        root = RunTree(
            id=_uuid_from_prefixed_id(run.trace_id),
            trace_id=_uuid_from_prefixed_id(run.trace_id),
            name="ticket_run",
            run_type="chain",
            start_time=run.started_at,
            inputs=inputs,
            extra={
                "metadata": {
                    "trace_id": run.trace_id,
                    "run_id": run.run_id,
                    "ticket_id": ticket.ticket_id,
                    **(metadata or {}),
                }
            },
            tags=["customer-support-copilot", "ticket-run"],
            project_name=self._project,
            ls_client=self._client,
        )
        try:
            root.post()
        except Exception:
            return None
        return root

    def create_child_run(
        self,
        *,
        parent: RunTree | None,
        event: TraceEvent,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> RunTree | None:
        if parent is None:
            return None
        child = parent.create_child(
            name=event.event_name,
            run_type=_langsmith_run_type_for_event(event.event_type),
            run_id=_uuid_from_prefixed_id(event.event_id),
            start_time=event.start_time,
            end_time=event.end_time,
            inputs=inputs or {},
            outputs=outputs,
            extra={
                "metadata": {
                    "trace_id": event.trace_id,
                    "run_id": event.run_id,
                    "ticket_id": event.ticket_id,
                    "event_type": event.event_type,
                    "node_name": event.node_name,
                    "status": event.status,
                    **(event.event_metadata or {}),
                }
            },
            tags=[f"event:{event.event_type}"],
        )
        try:
            child.post()
        except Exception:
            return None
        return child

    def finalize_run(
        self,
        *,
        root: RunTree | None,
        ended_at: datetime,
        outputs: dict[str, Any],
        error: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        if root is None:
            return
        root.end_time = ended_at
        root.outputs = outputs
        root.error = error
        existing_extra = dict(root.extra or {})
        metadata = dict(existing_extra.get("metadata") or {})
        metadata.update(extra_metadata or {})
        root.extra = {**existing_extra, "metadata": metadata}
        try:
            root.patch()
        except Exception:
            return


def _langsmith_run_type_for_event(event_type: str) -> str:
    if event_type == TraceEventType.LLM_CALL.value:
        return "llm"
    if event_type == TraceEventType.TOOL_CALL.value:
        return "tool"
    return "chain"


LangSmithTraceClient = LangSmithTraceExporter


__all__ = [
    "LangSmithTraceClient",
    "LangSmithTraceExporter",
    "NoOpTraceExporter",
    "TraceExporterProtocol",
]
