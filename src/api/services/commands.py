from __future__ import annotations

from src.db.models import Ticket
from src.tickets.message_log import IngestEmailPayload, MessageLogService
from src.tickets.state_machine import TicketStateService
from src.workers.runner import RunEnqueueResult, TicketRunner

from .base import TicketApiServiceBase
from .common import IdempotencyService


class TicketCommandServiceMixin:
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
    ) -> RunEnqueueResult:
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
                repositories=repositories,
                container=self._container,
                checkpointer=self._container.checkpointer,
            )
            result = runner.enqueue(
                ticket_id=ticket_id,
                ticket_version=ticket_version,
                trigger_type=trigger_type,
                force_retry=force_retry,
                actor_id=actor_id,
                request_id=request_id,
                state_service=state_service,
                allow_review_reentry=False,
            )
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

    def retry_ticket(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        actor_id: str | None,
        request_id: str | None,
        idempotency_key: str | None,
    ) -> RunEnqueueResult:
        return self.run_ticket(
            ticket_id=ticket_id,
            ticket_version=ticket_version,
            trigger_type="scheduled_retry",
            force_retry=True,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
