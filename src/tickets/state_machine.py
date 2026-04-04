from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from src.contracts.core import (
    CoreSchemaError,
    DraftQaStatus,
    DraftType,
    EntityIdPrefix,
    HumanReviewAction,
    InvalidStateTransitionError,
    LeaseConflictError,
    RunStatus,
    TicketBusinessStatus,
    TicketProcessingStatus,
    assert_expected_version,
    ensure_timezone_aware,
    generate_prefixed_id,
    normalize_ticket_routing,
    next_version,
    utc_now,
)
from src.db.models import DraftArtifact, HumanReview, Ticket, TicketRun
from src.db.repositories import RepositoryBundle, build_repository_bundle


DEFAULT_LEASE_DURATION = timedelta(minutes=5)
DEFAULT_CUSTOMER_INPUT_TTL = timedelta(days=14)
MAX_AUTOMATIC_RETRIES = 3
AUTOMATIC_RETRYABLE_ERROR_PREFIXES = ("llm_", "network_", "gmail_5")
_RESERVED_UPDATE_FIELDS = {
    "business_status",
    "processing_status",
    "version",
    "closed_at",
}
_LEASE_CLAIMABLE_PROCESSING_STATUSES = {
    TicketProcessingStatus.QUEUED,
    TicketProcessingStatus.ERROR,
}
_NON_CLAIMABLE_BUSINESS_STATUSES = {
    TicketBusinessStatus.APPROVED,
    TicketBusinessStatus.CLOSED,
}
_NON_RUNNABLE_BUSINESS_STATUSES = {
    TicketBusinessStatus.APPROVED,
    TicketBusinessStatus.CLOSED,
    TicketBusinessStatus.AWAITING_CUSTOMER_INPUT,
    TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
    TicketBusinessStatus.ESCALATED,
}
_RETRIABLE_RESET_PROCESSING_STATUSES = {
    TicketProcessingStatus.IDLE,
    TicketProcessingStatus.COMPLETED,
    TicketProcessingStatus.ERROR,
}
_WAITING_EXTERNAL_BUSINESS_STATUSES = {
    TicketBusinessStatus.AWAITING_CUSTOMER_INPUT,
    TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
    TicketBusinessStatus.ESCALATED,
}
_COMPLETED_RUN_BUSINESS_STATUSES = {
    TicketBusinessStatus.DRAFT_CREATED,
    TicketBusinessStatus.APPROVED,
    TicketBusinessStatus.ESCALATED,
    TicketBusinessStatus.CLOSED,
}
_APPROVAL_ACTIONS = {
    HumanReviewAction.APPROVE,
    HumanReviewAction.EDIT_AND_APPROVE,
}
_ROUTING_FIELDS = {
    "source_channel",
    "primary_route",
    "secondary_routes",
    "tags",
    "multi_intent",
}

_ALLOWED_BUSINESS_STATUS_TRANSITIONS: dict[
    TicketBusinessStatus,
    tuple[TicketBusinessStatus, ...],
] = {
    TicketBusinessStatus.NEW: (
        TicketBusinessStatus.TRIAGED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.TRIAGED: (
        TicketBusinessStatus.DRAFT_CREATED,
        TicketBusinessStatus.AWAITING_CUSTOMER_INPUT,
        TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
        TicketBusinessStatus.ESCALATED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.DRAFT_CREATED: (
        TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
        TicketBusinessStatus.ESCALATED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.AWAITING_CUSTOMER_INPUT: (
        TicketBusinessStatus.CLOSED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.AWAITING_HUMAN_REVIEW: (
        TicketBusinessStatus.APPROVED,
        TicketBusinessStatus.REJECTED,
        TicketBusinessStatus.ESCALATED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.APPROVED: (
        TicketBusinessStatus.CLOSED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.REJECTED: (
        TicketBusinessStatus.TRIAGED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.ESCALATED: (
        TicketBusinessStatus.CLOSED,
        TicketBusinessStatus.FAILED,
    ),
    TicketBusinessStatus.FAILED: (TicketBusinessStatus.TRIAGED,),
    TicketBusinessStatus.CLOSED: (),
}

_ALLOWED_PROCESSING_STATUS_TRANSITIONS: dict[
    TicketProcessingStatus,
    tuple[TicketProcessingStatus, ...],
] = {
    TicketProcessingStatus.IDLE: (TicketProcessingStatus.QUEUED,),
    TicketProcessingStatus.QUEUED: (TicketProcessingStatus.LEASED,),
    TicketProcessingStatus.LEASED: (
        TicketProcessingStatus.RUNNING,
        TicketProcessingStatus.QUEUED,
    ),
    TicketProcessingStatus.RUNNING: (
        TicketProcessingStatus.QUEUED,
        TicketProcessingStatus.WAITING_EXTERNAL,
        TicketProcessingStatus.COMPLETED,
        TicketProcessingStatus.ERROR,
    ),
    TicketProcessingStatus.WAITING_EXTERNAL: (
        TicketProcessingStatus.QUEUED,
        TicketProcessingStatus.COMPLETED,
    ),
    TicketProcessingStatus.COMPLETED: (TicketProcessingStatus.WAITING_EXTERNAL,),
    TicketProcessingStatus.ERROR: (
        TicketProcessingStatus.QUEUED,
        TicketProcessingStatus.LEASED,
        TicketProcessingStatus.COMPLETED,
    ),
}

_MANUAL_ACTION_ALLOWED_BUSINESS_STATUSES: dict[str, tuple[TicketBusinessStatus, ...]] = {
    HumanReviewAction.APPROVE.value: (TicketBusinessStatus.AWAITING_HUMAN_REVIEW,),
    HumanReviewAction.EDIT_AND_APPROVE.value: (
        TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
    ),
    HumanReviewAction.REJECT_FOR_REWRITE.value: (
        TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
    ),
    HumanReviewAction.ESCALATE.value: (
        TicketBusinessStatus.TRIAGED,
        TicketBusinessStatus.DRAFT_CREATED,
        TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
    ),
    "close": (
        TicketBusinessStatus.APPROVED,
        TicketBusinessStatus.AWAITING_CUSTOMER_INPUT,
        TicketBusinessStatus.ESCALATED,
        TicketBusinessStatus.FAILED,
    ),
}


@dataclass(frozen=True)
class TicketStatusUpdate:
    business_status: TicketBusinessStatus | None = None
    processing_status: TicketProcessingStatus | None = None
    fields: Mapping[str, Any] | None = None
    clear_error: bool = False
    closed_at: datetime | None = None
    clear_lease: bool = False


def get_allowed_business_status_transitions(
    current_status: TicketBusinessStatus | str,
) -> tuple[TicketBusinessStatus, ...]:
    normalized_status = TicketBusinessStatus(current_status)
    transitions = _ALLOWED_BUSINESS_STATUS_TRANSITIONS[normalized_status]
    if normalized_status is TicketBusinessStatus.CLOSED:
        return transitions
    if TicketBusinessStatus.FAILED in transitions:
        return transitions
    return transitions + (TicketBusinessStatus.FAILED,)


def get_allowed_processing_status_transitions(
    current_status: TicketProcessingStatus | str,
) -> tuple[TicketProcessingStatus, ...]:
    normalized_status = TicketProcessingStatus(current_status)
    return _ALLOWED_PROCESSING_STATUS_TRANSITIONS[normalized_status]


class TicketBusinessStateMachine:
    def can_transition(
        self,
        current_status: TicketBusinessStatus | str,
        target_status: TicketBusinessStatus | str,
    ) -> bool:
        normalized_current = TicketBusinessStatus(current_status)
        normalized_target = TicketBusinessStatus(target_status)
        return normalized_target in get_allowed_business_status_transitions(
            normalized_current
        )

    def assert_can_transition(
        self,
        current_status: TicketBusinessStatus | str,
        target_status: TicketBusinessStatus | str,
    ) -> None:
        normalized_current = TicketBusinessStatus(current_status)
        normalized_target = TicketBusinessStatus(target_status)
        if self.can_transition(normalized_current, normalized_target):
            return

        raise InvalidStateTransitionError(
            entity="ticket.business_status",
            current_status=normalized_current.value,
            target_status=normalized_target.value,
            allowed_transitions=[
                status.value
                for status in get_allowed_business_status_transitions(normalized_current)
            ],
        )


class TicketProcessingStateMachine:
    def can_transition(
        self,
        current_status: TicketProcessingStatus | str,
        target_status: TicketProcessingStatus | str,
    ) -> bool:
        normalized_current = TicketProcessingStatus(current_status)
        normalized_target = TicketProcessingStatus(target_status)
        return normalized_target in get_allowed_processing_status_transitions(
            normalized_current
        )

    def assert_can_transition(
        self,
        current_status: TicketProcessingStatus | str,
        target_status: TicketProcessingStatus | str,
    ) -> None:
        normalized_current = TicketProcessingStatus(current_status)
        normalized_target = TicketProcessingStatus(target_status)
        if self.can_transition(normalized_current, normalized_target):
            return

        raise InvalidStateTransitionError(
            entity="ticket.processing_status",
            current_status=normalized_current.value,
            target_status=normalized_target.value,
            allowed_transitions=[
                status.value
                for status in get_allowed_processing_status_transitions(normalized_current)
            ],
        )


class TicketStateService:
    def __init__(
        self,
        session: Session,
        *,
        repositories: RepositoryBundle | None = None,
        business_state_machine: TicketBusinessStateMachine | None = None,
        processing_state_machine: TicketProcessingStateMachine | None = None,
    ) -> None:
        self._session = session
        self._repositories = repositories or build_repository_bundle(session)
        self._business_state_machine = (
            business_state_machine or TicketBusinessStateMachine()
        )
        self._processing_state_machine = (
            processing_state_machine or TicketProcessingStateMachine()
        )

    def transition_business_status(
        self,
        ticket_id: str,
        *,
        target_status: TicketBusinessStatus | str,
        expected_version: int | None = None,
        metadata_updates: Mapping[str, Any] | None = None,
        closed_at: datetime | None = None,
        clear_error: bool = False,
    ) -> Ticket:
        return self.update_ticket_statuses(
            ticket_id,
            expected_version=expected_version,
            update=TicketStatusUpdate(
                business_status=TicketBusinessStatus(target_status),
                fields=metadata_updates,
                closed_at=closed_at,
                clear_error=clear_error,
            ),
        )

    def update_ticket_statuses(
        self,
        ticket_id: str,
        *,
        expected_version: int | None = None,
        update: TicketStatusUpdate,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )

        return self._update_ticket(ticket, update=update)

    def _update_ticket(
        self,
        ticket: Ticket,
        *,
        update: TicketStatusUpdate,
    ) -> Ticket:

        self._validate_status_update(ticket, update)
        self._apply_status_update(ticket, update)
        return ticket

    def claim_ticket(
        self,
        ticket_id: str,
        *,
        worker_id: str,
        run_id: str,
        expected_version: int | None = None,
        now: datetime | None = None,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )

        current_time = ensure_timezone_aware(now or utc_now())
        run = self._repositories.ticket_runs.get(run_id)
        if run is None or run.ticket_id != ticket.ticket_id:
            self._raise_invalid_transition(
                entity="ticket.current_run_id",
                current_status=ticket.current_run_id or "",
                target_status=run_id,
                reason="Ticket claim requires an existing run bound to the same ticket.",
            )
        if run.status != RunStatus.QUEUED.value:
            self._raise_invalid_transition(
                entity="ticket_run.status",
                current_status=run.status,
                target_status=RunStatus.RUNNING.value,
                reason="Worker can only claim runs that are queued.",
            )
        self._assert_processing_status_in(
            ticket,
            allowed_statuses=_LEASE_CLAIMABLE_PROCESSING_STATUSES,
            target_status=TicketProcessingStatus.LEASED.value,
            reason="Only queued or error tickets can be claimed.",
        )
        self._assert_business_status_not_in(
            ticket,
            disallowed_statuses=_NON_CLAIMABLE_BUSINESS_STATUSES,
            target_status=ticket.business_status,
            reason="Approved or closed tickets cannot be claimed.",
        )
        self._assert_lease_available(ticket, current_time)

        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                processing_status=TicketProcessingStatus.LEASED,
                fields={
                    "lease_owner": worker_id,
                    "lease_expires_at": current_time + lease_duration,
                    "current_run_id": run_id,
                },
            ),
        )

    def enqueue_ticket_run(
        self,
        ticket_id: str,
        *,
        run_id: str,
        expected_version: int | None = None,
        force_retry: bool = False,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )

        if TicketBusinessStatus(ticket.business_status) is TicketBusinessStatus.FAILED:
            return self.requeue_failed_ticket(
                ticket_id,
                expected_version=expected_version,
                run_id=run_id,
                force_retry=force_retry,
            )

        self._assert_business_status_not_in(
            ticket,
            disallowed_statuses=_NON_RUNNABLE_BUSINESS_STATUSES,
            target_status=TicketProcessingStatus.QUEUED.value,
            reason="Ticket is not in a runnable business state.",
        )

        current_time = ensure_timezone_aware(utc_now())
        self._assert_lease_available(ticket, current_time)

        existing_run_id = ticket.current_run_id
        if existing_run_id and existing_run_id != run_id:
            existing_run = self._repositories.ticket_runs.get(existing_run_id)
            if existing_run is not None and existing_run.ended_at is None:
                self._raise_invalid_transition(
                    entity="ticket.current_run_id",
                    current_status=existing_run.status,
                    target_status=RunStatus.QUEUED.value,
                    reason="Ticket already has an active queued or running run.",
                )

        if TicketBusinessStatus(ticket.business_status) in {
            TicketBusinessStatus.NEW,
            TicketBusinessStatus.REJECTED,
        } or TicketProcessingStatus(ticket.processing_status) in _RETRIABLE_RESET_PROCESSING_STATUSES:
            target_business_status = TicketBusinessStatus.TRIAGED
        else:
            target_business_status = TicketBusinessStatus(ticket.business_status)

        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                business_status=target_business_status,
                processing_status=TicketProcessingStatus.QUEUED,
                fields={"current_run_id": run_id},
                clear_error=True,
                clear_lease=True,
            ),
        )

    def start_run(
        self,
        ticket_id: str,
        *,
        worker_id: str,
        run_id: str | None = None,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        self._assert_valid_lease(ticket, worker_id=worker_id, run_id=run_id, now=now)
        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                processing_status=TicketProcessingStatus.RUNNING,
            ),
        )

    def renew_lease(
        self,
        ticket_id: str,
        *,
        worker_id: str,
        run_id: str | None = None,
        now: datetime | None = None,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
        expected_version: int | None = None,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        current_time = ensure_timezone_aware(now or utc_now())
        self._assert_valid_lease(
            ticket,
            worker_id=worker_id,
            run_id=run_id,
            now=current_time,
        )
        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                fields={"lease_expires_at": current_time + lease_duration},
            ),
        )

    def fail_run(
        self,
        ticket_id: str,
        *,
        worker_id: str,
        run_id: str | None = None,
        error_code: str,
        error_message: str,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        self._assert_valid_lease(ticket, worker_id=worker_id, run_id=run_id, now=now)
        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                business_status=TicketBusinessStatus.FAILED,
                processing_status=TicketProcessingStatus.ERROR,
                fields={
                    "last_error_code": error_code,
                    "last_error_message": error_message,
                },
                clear_lease=True,
            ),
        )

    def mark_waiting_external(
        self,
        ticket_id: str,
        *,
        worker_id: str,
        run_id: str | None = None,
        business_status: TicketBusinessStatus | str,
        expected_version: int | None = None,
        metadata_updates: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        self._assert_valid_lease(ticket, worker_id=worker_id, run_id=run_id, now=now)
        normalized_business_status = TicketBusinessStatus(business_status)
        self._assert_business_status_value_in(
            ticket,
            status=normalized_business_status,
            allowed_statuses=_WAITING_EXTERNAL_BUSINESS_STATUSES,
            reason=(
                "waiting_external is only valid for awaiting_customer_input, "
                "awaiting_human_review, or escalated tickets."
            ),
        )
        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                business_status=normalized_business_status,
                processing_status=TicketProcessingStatus.WAITING_EXTERNAL,
                fields=metadata_updates,
                clear_lease=True,
            ),
        )

    def complete_run(
        self,
        ticket_id: str,
        *,
        worker_id: str,
        run_id: str | None = None,
        business_status: TicketBusinessStatus | str,
        expected_version: int | None = None,
        metadata_updates: Mapping[str, Any] | None = None,
        closed_at: datetime | None = None,
        clear_error: bool = True,
        now: datetime | None = None,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        self._assert_valid_lease(ticket, worker_id=worker_id, run_id=run_id, now=now)
        normalized_business_status = TicketBusinessStatus(business_status)
        self._assert_business_status_value_in(
            ticket,
            status=normalized_business_status,
            allowed_statuses=_COMPLETED_RUN_BUSINESS_STATUSES,
            reason=(
                "completed is only valid for draft_created, approved, "
                "escalated, or closed tickets."
            ),
        )
        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                business_status=normalized_business_status,
                processing_status=TicketProcessingStatus.COMPLETED,
                fields=metadata_updates,
                closed_at=closed_at,
                clear_error=clear_error,
                clear_lease=True,
            ),
        )

    def requeue_failed_ticket(
        self,
        ticket_id: str,
        *,
        worker_id: str | None = None,
        run_id: str | None = None,
        expected_version: int | None = None,
        now: datetime | None = None,
        force_retry: bool = False,
        clear_error: bool = True,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        self._assert_business_status_in(
            ticket,
            allowed_statuses={TicketBusinessStatus.FAILED},
            target_status=TicketBusinessStatus.TRIAGED.value,
            reason="Only failed tickets can be re-queued for retry.",
        )
        self._assert_processing_status_in(
            ticket,
            allowed_statuses={TicketProcessingStatus.ERROR},
            target_status=TicketProcessingStatus.QUEUED.value,
            reason="Only error tickets can be re-queued for retry.",
        )
        if not force_retry and not self.can_retry_automatically(ticket):
            self._raise_invalid_transition(
                entity="ticket.business_status",
                current_status=ticket.business_status,
                target_status=TicketBusinessStatus.TRIAGED.value,
                reason="Ticket is not eligible for automatic retry.",
            )

        fields: dict[str, Any] = {"current_run_id": run_id}
        if worker_id is not None:
            fields["lease_owner"] = worker_id
        if now is not None:
            fields["lease_expires_at"] = ensure_timezone_aware(now)

        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                business_status=TicketBusinessStatus.TRIAGED,
                processing_status=TicketProcessingStatus.QUEUED,
                fields=fields,
                clear_error=clear_error,
                clear_lease=True,
            ),
        )

    def reclaim_expired_lease(
        self,
        ticket_id: str,
        *,
        now: datetime | None = None,
        expected_version: int | None = None,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        current_time = ensure_timezone_aware(now or utc_now())
        lease_expires_at = _normalize_optional_datetime(ticket.lease_expires_at)
        if lease_expires_at is None or lease_expires_at > current_time:
            raise LeaseConflictError(
                ticket_id=ticket.ticket_id,
                lease_owner=ticket.lease_owner,
                message=f"Ticket `{ticket.ticket_id}` lease has not expired yet.",
            )
        if ticket.current_run_id:
            current_run = self._repositories.ticket_runs.get(ticket.current_run_id)
            if current_run is not None and current_run.ended_at is None:
                current_run.status = RunStatus.QUEUED.value
        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                processing_status=TicketProcessingStatus.QUEUED,
                clear_lease=True,
            ),
        )

    def ensure_draft_idempotency(
        self,
        *,
        ticket_id: str,
        draft_type: DraftType | str,
        version_index: int,
    ) -> DraftArtifact | None:
        ticket = self._get_ticket(ticket_id)
        if TicketBusinessStatus(ticket.business_status) is TicketBusinessStatus.CLOSED:
            raise InvalidStateTransitionError(
                entity="ticket.business_status",
                current_status=ticket.business_status,
                target_status=TicketBusinessStatus.CLOSED.value,
                reason="Closed tickets cannot create new Gmail drafts.",
            )

        idempotency_key = self.build_draft_idempotency_key(
            ticket_id=ticket_id,
            draft_type=draft_type,
            version_index=version_index,
        )
        matching_drafts = [
            draft
            for draft in self._repositories.draft_artifacts.list_by_ticket(ticket_id)
            if draft.idempotency_key == idempotency_key
        ]
        if not matching_drafts:
            return None

        matching_drafts.sort(key=lambda draft: draft.created_at)
        existing_draft = matching_drafts[-1]
        if existing_draft.gmail_draft_id:
            return existing_draft

        for draft in matching_drafts[:-1]:
            if draft.gmail_draft_id:
                return draft

        return existing_draft

    def validate_manual_action_precondition(
        self,
        ticket_id: str,
        *,
        action: str,
        expected_version: int | None = None,
    ) -> Ticket:
        ticket = self._get_ticket_for_update(
            ticket_id,
            expected_version=expected_version,
        )
        allowed_statuses = _MANUAL_ACTION_ALLOWED_BUSINESS_STATUSES.get(action)
        if allowed_statuses is None:
            raise CoreSchemaError(f"Unsupported manual action `{action}`.")
        current_status = TicketBusinessStatus(ticket.business_status)
        if current_status not in allowed_statuses:
            raise InvalidStateTransitionError(
                entity="ticket.business_status",
                current_status=current_status.value,
                target_status=action,
                allowed_transitions=[status.value for status in allowed_statuses],
            )
        return ticket

    def apply_manual_review_action(
        self,
        *,
        ticket_id: str,
        action: HumanReviewAction | str,
        reviewer_id: str,
        ticket_version_at_review: int,
        draft_id: str | None = None,
        comment: str | None = None,
        edited_content_text: str | None = None,
        edited_content_html: str | None = None,
        rewrite_reasons: Iterable[str] | None = None,
        target_queue: str | None = None,
        run_id: str | None = None,
    ) -> tuple[Ticket, HumanReview]:
        normalized_action = HumanReviewAction(action)
        ticket = self.validate_manual_action_precondition(
            ticket_id,
            action=normalized_action.value,
            expected_version=ticket_version_at_review,
        )

        review = HumanReview(
            review_id=self._build_review_id(ticket),
            ticket_id=ticket.ticket_id,
            draft_id=draft_id,
            reviewer_id=reviewer_id,
            action=normalized_action.value,
            comment=comment,
            edited_content_text=edited_content_text,
            edited_content_html=edited_content_html,
            requested_rewrite_reason=(
                {"reasons": list(rewrite_reasons or [])}
                if normalized_action is HumanReviewAction.REJECT_FOR_REWRITE
                else None
            ),
            target_queue=target_queue,
            ticket_version_at_review=ticket_version_at_review,
            created_at=utc_now(),
        )
        self._repositories.human_reviews.add(review)

        if normalized_action is HumanReviewAction.EDIT_AND_APPROVE:
            if not run_id:
                raise CoreSchemaError(
                    "edit_and_approve requires run_id to create a new DraftArtifact."
                )
            if not edited_content_text:
                raise CoreSchemaError(
                    "edit_and_approve requires edited_content_text."
                )
            new_draft = DraftArtifact(
                draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
                ticket_id=ticket.ticket_id,
                run_id=run_id,
                version_index=self._get_next_draft_version_index(ticket.ticket_id),
                draft_type=DraftType.REPLY.value,
                content_text=edited_content_text,
                content_html=edited_content_html,
                qa_status=DraftQaStatus.PASSED.value,
                idempotency_key=None,
                created_at=utc_now(),
            )
            self._repositories.draft_artifacts.add(new_draft)

        if normalized_action in _APPROVAL_ACTIONS:
            update = TicketStatusUpdate(
                business_status=TicketBusinessStatus.APPROVED,
                processing_status=TicketProcessingStatus.COMPLETED,
            )
        elif normalized_action is HumanReviewAction.REJECT_FOR_REWRITE:
            update = TicketStatusUpdate(
                business_status=TicketBusinessStatus.REJECTED,
                processing_status=TicketProcessingStatus.QUEUED,
            )
        else:
            update = TicketStatusUpdate(
                business_status=TicketBusinessStatus.ESCALATED,
                processing_status=TicketProcessingStatus.WAITING_EXTERNAL,
                fields={"risk_reasons": ticket.risk_reasons},
                clear_lease=True,
            )

        updated_ticket = self._update_ticket(
            ticket,
            update=update,
        )

        return updated_ticket, review

    def apply_close_action(
        self,
        *,
        ticket_id: str,
        ticket_version: int,
        reason: str,
        closed_at: datetime | None = None,
    ) -> Ticket:
        ticket = self.validate_manual_action_precondition(
            ticket_id,
            action="close",
            expected_version=ticket_version,
        )
        return self._update_ticket(
            ticket,
            update=TicketStatusUpdate(
                business_status=TicketBusinessStatus.CLOSED,
                processing_status=TicketProcessingStatus.COMPLETED,
                fields={"routing_reason": reason},
                closed_at=closed_at,
                clear_lease=True,
            ),
        )

    def can_retry_automatically(self, ticket: Ticket) -> bool:
        error_code = (ticket.last_error_code or "").lower()
        if not error_code or not error_code.startswith(AUTOMATIC_RETRYABLE_ERROR_PREFIXES):
            return False
        return self.get_automatic_retry_count(ticket.ticket_id) < MAX_AUTOMATIC_RETRIES

    def get_automatic_retry_count(self, ticket_id: str) -> int:
        return sum(
            1
            for run in self._repositories.ticket_runs.list_by_ticket(ticket_id)
            if run.trigger_type == "scheduled_retry"
        )

    def get_next_run_attempt_index(self, ticket_id: str) -> int:
        runs = self._repositories.ticket_runs.list_by_ticket(ticket_id)
        if not runs:
            return 1
        return max(run.attempt_index for run in runs) + 1

    def _get_ticket(self, ticket_id: str) -> Ticket:
        ticket = self._repositories.tickets.get(ticket_id)
        if ticket is None:
            raise CoreSchemaError(f"Ticket `{ticket_id}` does not exist.")
        return ticket

    def _get_ticket_for_update(
        self,
        ticket_id: str,
        *,
        expected_version: int | None = None,
    ) -> Ticket:
        ticket = self._get_ticket(ticket_id)
        if expected_version is not None:
            assert_expected_version(
                expected=expected_version,
                actual=ticket.version,
                entity="ticket",
            )
        return ticket

    def _validate_status_update(
        self,
        ticket: Ticket,
        update: TicketStatusUpdate,
    ) -> None:
        if update.business_status is not None:
            self._business_state_machine.assert_can_transition(
                ticket.business_status,
                update.business_status,
            )
        if update.processing_status is not None:
            current_processing_status = TicketProcessingStatus(ticket.processing_status)
            target_processing_status = TicketProcessingStatus(update.processing_status)
            if target_processing_status is not current_processing_status:
                self._processing_state_machine.assert_can_transition(
                    current_processing_status,
                    target_processing_status,
                )

        fields = dict(update.fields or {})
        conflicting_fields = sorted(_RESERVED_UPDATE_FIELDS.intersection(fields.keys()))
        if conflicting_fields:
            conflict_text = ", ".join(conflicting_fields)
            raise CoreSchemaError(
                f"fields cannot override reserved fields: {conflict_text}."
            )
        for field_name in fields:
            if not hasattr(ticket, field_name):
                raise CoreSchemaError(
                    f"Ticket has no persisted field named `{field_name}`."
                )
        if update.closed_at is not None:
            ensure_timezone_aware(update.closed_at)

    def _apply_status_update(
        self,
        ticket: Ticket,
        update: TicketStatusUpdate,
    ) -> None:
        fields = dict(update.fields or {})

        if update.business_status is not None:
            ticket.business_status = update.business_status.value
        if update.processing_status is not None:
            ticket.processing_status = update.processing_status.value

        if update.business_status is TicketBusinessStatus.CLOSED:
            ticket.closed_at = update.closed_at or utc_now()
        elif update.business_status is not None:
            ticket.closed_at = None

        if update.clear_error:
            ticket.last_error_code = None
            ticket.last_error_message = None

        for field_name, value in fields.items():
            setattr(ticket, field_name, value)

        if self._routing_fields_updated(fields):
            selection = normalize_ticket_routing(
                source_channel=ticket.source_channel,
                primary_route=ticket.primary_route,
                secondary_routes=ticket.secondary_routes or [],
                tags=ticket.tags or [],
                multi_intent=bool(ticket.multi_intent),
            )
            ticket.source_channel = selection.source_channel.value
            ticket.primary_route = (
                selection.primary_route.value
                if selection.primary_route is not None
                else None
            )
            ticket.secondary_routes = [
                route.value for route in selection.secondary_routes
            ]
            ticket.tags = [tag.value for tag in selection.tags]
            ticket.multi_intent = selection.multi_intent

        if update.clear_lease:
            ticket.lease_owner = None
            ticket.lease_expires_at = None

        ticket.version = next_version(ticket.version)

    def _routing_fields_updated(self, fields: Mapping[str, Any]) -> bool:
        return bool(_ROUTING_FIELDS.intersection(fields.keys()))

    def _raise_invalid_transition(
        self,
        *,
        entity: str,
        current_status: str,
        target_status: str,
        reason: str,
    ) -> None:
        raise InvalidStateTransitionError(
            entity=entity,
            current_status=current_status,
            target_status=target_status,
            reason=reason,
        )

    def _assert_business_status_in(
        self,
        ticket: Ticket,
        *,
        allowed_statuses: set[TicketBusinessStatus],
        target_status: str,
        reason: str,
    ) -> None:
        current_status = TicketBusinessStatus(ticket.business_status)
        if current_status in allowed_statuses:
            return
        self._raise_invalid_transition(
            entity="ticket.business_status",
            current_status=current_status.value,
            target_status=target_status,
            reason=reason,
        )

    def _assert_business_status_not_in(
        self,
        ticket: Ticket,
        *,
        disallowed_statuses: set[TicketBusinessStatus],
        target_status: str,
        reason: str,
    ) -> None:
        current_status = TicketBusinessStatus(ticket.business_status)
        if current_status not in disallowed_statuses:
            return
        self._raise_invalid_transition(
            entity="ticket.business_status",
            current_status=current_status.value,
            target_status=target_status,
            reason=reason,
        )

    def _assert_business_status_value_in(
        self,
        ticket: Ticket,
        *,
        status: TicketBusinessStatus,
        allowed_statuses: set[TicketBusinessStatus],
        reason: str,
    ) -> None:
        if status in allowed_statuses:
            return
        self._raise_invalid_transition(
            entity="ticket.business_status",
            current_status=ticket.business_status,
            target_status=status.value,
            reason=reason,
        )

    def _assert_processing_status_in(
        self,
        ticket: Ticket,
        *,
        allowed_statuses: set[TicketProcessingStatus],
        target_status: str,
        reason: str,
    ) -> None:
        current_status = TicketProcessingStatus(ticket.processing_status)
        if current_status in allowed_statuses:
            return
        self._raise_invalid_transition(
            entity="ticket.processing_status",
            current_status=current_status.value,
            target_status=target_status,
            reason=reason,
        )

    def _assert_lease_available(self, ticket: Ticket, now: datetime) -> None:
        if self._lease_is_available(ticket, now):
            return
        raise LeaseConflictError(
            ticket_id=ticket.ticket_id,
            lease_owner=ticket.lease_owner,
            message=(
                f"Ticket `{ticket.ticket_id}` is currently leased by "
                f"`{ticket.lease_owner}`."
            ),
        )

    def _lease_is_available(self, ticket: Ticket, now: datetime) -> bool:
        lease_expires_at = _normalize_optional_datetime(ticket.lease_expires_at)
        if lease_expires_at is None:
            return True
        return lease_expires_at <= now

    def _assert_valid_lease(
        self,
        ticket: Ticket,
        *,
        worker_id: str,
        run_id: str | None = None,
        now: datetime | None = None,
    ) -> None:
        current_time = ensure_timezone_aware(now or utc_now())
        if ticket.lease_owner != worker_id:
            raise LeaseConflictError(
                ticket_id=ticket.ticket_id,
                lease_owner=ticket.lease_owner,
                message=(
                    f"Ticket `{ticket.ticket_id}` lease is owned by "
                    f"`{ticket.lease_owner}`."
                ),
            )
        if run_id is not None and ticket.current_run_id != run_id:
            raise LeaseConflictError(
                ticket_id=ticket.ticket_id,
                lease_owner=ticket.lease_owner,
                message=(
                    f"Ticket `{ticket.ticket_id}` lease is associated with "
                    f"run `{ticket.current_run_id}`, not `{run_id}`."
                ),
            )
        lease_expires_at = _normalize_optional_datetime(ticket.lease_expires_at)
        if lease_expires_at is None or lease_expires_at <= current_time:
            raise LeaseConflictError(
                ticket_id=ticket.ticket_id,
                lease_owner=ticket.lease_owner,
                message=f"Ticket `{ticket.ticket_id}` lease is expired.",
            )

    def build_draft_idempotency_key(
        self,
        *,
        ticket_id: str,
        draft_type: DraftType | str,
        version_index: int,
    ) -> str:
        normalized_type = DraftType(draft_type)
        if version_index < 1:
            raise CoreSchemaError("version_index must be >= 1 for Gmail draft idempotency.")
        return f"draft:{ticket_id}:{normalized_type.value}:{version_index}"

    def _get_next_draft_version_index(self, ticket_id: str) -> int:
        drafts = self._repositories.draft_artifacts.list_by_ticket(ticket_id)
        if not drafts:
            return 1
        return max(draft.version_index for draft in drafts) + 1

    def _build_review_id(self, ticket: Ticket) -> str:
        return generate_prefixed_id(EntityIdPrefix.REVIEW)


def _normalize_optional_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=utc_now().tzinfo)
    return ensure_timezone_aware(value)

