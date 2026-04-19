from __future__ import annotations

from sqlalchemy.orm import Session

from src.api.service_errors import TicketNotFoundError
from src.contracts.core import (
    EntityIdPrefix,
    HumanReviewAction,
    MemorySourceStage,
    RunFinalAction,
    RunStatus,
    RunTriggerType,
    TicketBusinessStatus,
    generate_prefixed_id,
    utc_now,
)
from src.db.models import Ticket, TicketRun
from src.memory import CustomerMemoryService
from src.telemetry.metrics import duration_ms
from src.tickets.state_machine import TicketStateService

from .base import TicketApiServiceBase
from .common import IdempotencyService


class TicketManualActionServiceMixin:
    def save_ticket_draft(
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
        return self._save_edited_draft(
            ticket_id=ticket_id,
            ticket_version=ticket_version,
            draft_id=draft_id,
            comment=comment,
            edited_content_text=edited_content_text,
            actor_id=actor_id,
            action=HumanReviewAction.SAVE_DRAFT,
            final_action=RunFinalAction.NO_OP.value,
            idempotency_key=idempotency_key,
        )

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
        return self._save_edited_draft(
            ticket_id=ticket_id,
            ticket_version=ticket_version,
            draft_id=draft_id,
            comment=comment,
            edited_content_text=edited_content_text,
            actor_id=actor_id,
            action=HumanReviewAction.EDIT_AND_APPROVE,
            final_action=RunFinalAction.HANDOFF_TO_HUMAN.value,
            idempotency_key=idempotency_key,
        )

    def _save_edited_draft(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        draft_id: str,
        comment: str | None,
        edited_content_text: str,
        actor_id: str,
        action: HumanReviewAction,
        final_action: str,
        idempotency_key: str | None = None,
    ) -> tuple[Ticket, str]:
        key_to_use = idempotency_key or (
            f"manual:{ticket_id}:{action.value}:{ticket_version}:{draft_id}:{actor_id}"
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

            run = self._create_action_run(
                session=session,
                repositories=repositories,
                ticket=ticket,
                trigger_type=RunTriggerType.HUMAN_ACTION,
                actor_id=actor_id,
                state_service=state_service,
            )
            updated, review = state_service.apply_manual_review_action(
                ticket_id=ticket_id,
                action=action,
                reviewer_id=actor_id,
                ticket_version_at_review=ticket_version,
                draft_id=draft_id,
                comment=comment,
                edited_content_text=edited_content_text,
                run_id=run.run_id,
            )
            self._complete_action_run(
                run=run,
                final_action=final_action,
            )
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
            run = self._create_action_run(
                session=session,
                repositories=repositories,
                ticket=updated,
                trigger_type=RunTriggerType.HUMAN_ACTION,
                actor_id=actor_id,
                state_service=state_service,
            )
            CustomerMemoryService(
                session,
                repositories=repositories,
                extractor=self._container.memory_extractor,
            ).apply_stage_updates(
                ticket=updated,
                run=run,
                stage=MemorySourceStage.CLOSE_TICKET,
                review_comment=reason,
            )
            self._complete_action_run(
                run=run,
                final_action=RunFinalAction.CLOSE_TICKET.value,
            )
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
            run = self._create_action_run(
                session=session,
                repositories=repositories,
                ticket=updated,
                trigger_type=RunTriggerType.HUMAN_ACTION,
                actor_id=actor_id,
                state_service=state_service,
            )
            if action is HumanReviewAction.ESCALATE:
                CustomerMemoryService(
                    session,
                    repositories=repositories,
                    extractor=self._container.memory_extractor,
                ).apply_stage_updates(
                    ticket=updated,
                    run=run,
                    stage=MemorySourceStage.ESCALATE_TO_HUMAN,
                    review_comment=comment,
                    target_queue=target_queue,
                )
            self._complete_action_run(
                run=run,
                final_action=self._manual_action_final_action(action, updated),
            )
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

    def _create_action_run(
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

    def _complete_action_run(
        self,
        *,
        run: TicketRun,
        final_action: str,
    ) -> None:
        run.status = RunStatus.SUCCEEDED.value
        run.final_action = final_action
        run.ended_at = utc_now()
        run.latency_metrics = {
            "end_to_end_ms": duration_ms(run.started_at, run.ended_at)
        }

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
