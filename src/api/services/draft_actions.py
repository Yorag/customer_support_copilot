from __future__ import annotations

from src.api.service_errors import TicketNotFoundError
from src.workers.runner import RunEnqueueResult, TicketRunner
from src.tickets.state_machine import TicketStateService

from .base import TicketApiServiceBase
from .common import IdempotencyService


class TicketDraftActionServiceMixin(TicketApiServiceBase):
    def generate_ticket_draft(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        actor_id: str,
        request_id: str | None,
        idempotency_key: str | None,
        mode: str,
        source_draft_id: str | None = None,
        comment: str | None = None,
        rewrite_guidance: list[str] | None = None,
    ) -> RunEnqueueResult:
        key_to_use = idempotency_key or (
            f"generate-draft:{ticket_id}:{ticket_version}:{mode}:{source_draft_id or ''}:{request_id or ''}"
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
            runner = TicketRunner(
                session=session,
                repositories=repositories,
                container=self._container,
                checkpointer=self._container.checkpointer,
            )
            result = runner.enqueue(
                ticket_id=ticket_id,
                ticket_version=ticket_version,
                trigger_type="manual_api",
                force_retry=False,
                actor_id=actor_id,
                request_id=request_id,
                state_service=state_service,
                allow_review_reentry=True,
            )
            result.run.app_metadata = {
                **(result.run.app_metadata or {}),
                "draft_request": {
                    "mode": mode,
                    "source_draft_id": source_draft_id,
                    "comment": comment,
                    "rewrite_guidance": list(rewrite_guidance or []),
                },
            }
            session.flush()
            idempotency.record(
                key_to_use,
                {
                    "ticket_id": result.ticket.ticket_id,
                    "run_id": result.run.run_id,
                    "trace_id": result.run.trace_id,
                    "mode": mode,
                    "source_draft_id": source_draft_id,
                    "rewrite_guidance": list(rewrite_guidance or []),
                },
            )
            return result
