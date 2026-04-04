from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contracts.core import (
    CoreSchemaError,
    DraftType,
    EntityIdPrefix,
    HumanReviewAction,
    InvalidStateTransitionError,
    LeaseConflictError,
    VersionConflictError,
    generate_prefixed_id,
)
from src.db.base import Base
from src.db.models import DraftArtifact, Ticket, TicketRun
from src.db.session import build_engine, create_session_factory, session_scope
from src.tickets.state_machine import (
    TicketBusinessStateMachine,
    TicketProcessingStateMachine,
    TicketStateService,
    get_allowed_business_status_transitions,
    get_allowed_processing_status_transitions,
)


def _build_ticket(
    *,
    business_status: str = "new",
    processing_status: str = "queued",
    version: int = 1,
    current_run_id: str | None = None,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
) -> Ticket:
    return Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="gmail-thread-state-machine",
        source_message_id="<msg-state-machine@gmail.com>",
        gmail_thread_id="gmail-thread-state-machine",
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject="Need help",
        business_status=business_status,
        processing_status=processing_status,
        priority="medium",
        secondary_routes=[],
        tags=[],
        multi_intent=False,
        needs_clarification=False,
        needs_escalation=False,
        risk_reasons=[],
        version=version,
        current_run_id=current_run_id,
        lease_owner=lease_owner,
        lease_expires_at=lease_expires_at,
    )


def _build_run(ticket_id: str, *, trigger_type: str = "manual_api", attempt_index: int = 1) -> TicketRun:
    return TicketRun(
        run_id=generate_prefixed_id(EntityIdPrefix.RUN),
        ticket_id=ticket_id,
        trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
        trigger_type=trigger_type,
        status="running",
        started_at=datetime.now(timezone.utc),
        attempt_index=attempt_index,
    )


def test_get_allowed_business_status_transitions_matches_spec_for_triaged():
    allowed = get_allowed_business_status_transitions("triaged")

    assert [status.value for status in allowed] == [
        "draft_created",
        "awaiting_customer_input",
        "awaiting_human_review",
        "escalated",
        "failed",
    ]


def test_get_allowed_processing_status_transitions_matches_spec_for_running():
    allowed = get_allowed_processing_status_transitions("running")

    assert [status.value for status in allowed] == [
        "queued",
        "waiting_external",
        "completed",
        "error",
    ]


def test_transition_updates_ticket_fields_and_increments_version():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket()
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        updated_ticket = service.transition_business_status(
            ticket.ticket_id,
            target_status="triaged",
            expected_version=1,
            metadata_updates={
                "primary_route": "technical_issue",
                "secondary_routes": ["knowledge_request"],
                "tags": ["needs_clarification"],
                "priority": "high",
                "intent_confidence": 0.87,
                "multi_intent": True,
                "routing_reason": "Customer reported a technical problem with missing steps.",
            },
        )

        assert updated_ticket.business_status == "triaged"
        assert updated_ticket.version == 2
        assert updated_ticket.primary_route == "technical_issue"
        assert updated_ticket.secondary_routes == ["knowledge_request"]
        assert updated_ticket.tags == ["needs_clarification", "multi_intent"]
        assert updated_ticket.priority == "high"
        assert float(updated_ticket.intent_confidence) == pytest.approx(0.87)
        assert updated_ticket.routing_reason == (
            "Customer reported a technical problem with missing steps."
        )
        assert updated_ticket.closed_at is None


def test_transition_to_closed_sets_closed_at_when_missing():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="approved",
            processing_status="completed",
            version=7,
        )
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        updated = service.apply_close_action(
            ticket_id=ticket.ticket_id,
            ticket_version=7,
            reason="draft_sent_manually",
        )

        assert updated.business_status == "closed"
        assert updated.processing_status == "completed"
        assert updated.version == 8
        assert updated.closed_at is not None
        assert updated.closed_at.tzinfo is not None


def test_invalid_transition_raises_invalid_state_transition_error():
    machine = TicketBusinessStateMachine()

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        machine.assert_can_transition("draft_created", "approved")

    error = exc_info.value
    assert error.current_status == "draft_created"
    assert error.target_status == "approved"
    assert error.allowed_transitions == (
        "awaiting_human_review",
        "escalated",
        "failed",
    )


def test_claim_ticket_sets_lease_fields_and_increments_version():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(version=3)
        session.add(ticket)
        session.add(
            TicketRun(
                run_id="run-001",
                ticket_id=ticket.ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="queued",
                attempt_index=1,
            )
        )
        session.flush()

        service = TicketStateService(session)
        updated = service.claim_ticket(
            ticket.ticket_id,
            worker_id="worker-a",
            run_id="run-001",
            expected_version=3,
            now=now,
        )

        assert updated.processing_status == "leased"
        assert updated.lease_owner == "worker-a"
        assert updated.current_run_id == "run-001"
        assert updated.lease_expires_at == now + timedelta(minutes=5)
        assert updated.version == 4


def test_enqueue_ticket_run_sets_current_run_id_and_keeps_ticket_queued():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(version=3)
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        updated = service.enqueue_ticket_run(
            ticket.ticket_id,
            run_id="run-enqueued-1",
            expected_version=3,
        )

        assert updated.business_status == "triaged"
        assert updated.processing_status == "queued"
        assert updated.current_run_id == "run-enqueued-1"
        assert updated.lease_owner is None
        assert updated.lease_expires_at is None
        assert updated.version == 4


def test_enqueue_ticket_run_rejects_existing_active_run():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        existing_run = TicketRun(
            run_id="run-existing",
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="queued",
            attempt_index=1,
        )
        ticket = _build_ticket(
            business_status="triaged",
            processing_status="queued",
            version=3,
            current_run_id=existing_run.run_id,
        )
        existing_run.ticket_id = ticket.ticket_id
        session.add(ticket)
        session.add(existing_run)
        session.flush()

        service = TicketStateService(session)

        with pytest.raises(InvalidStateTransitionError):
            service.enqueue_ticket_run(
                ticket.ticket_id,
                run_id="run-next",
                expected_version=3,
            )


def test_claim_ticket_rejects_active_lease():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            processing_status="queued",
            lease_owner="worker-a",
            lease_expires_at=now + timedelta(minutes=1),
            current_run_id="run-002",
        )
        session.add(ticket)
        session.add(
            TicketRun(
                run_id="run-002",
                ticket_id=ticket.ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="queued",
                attempt_index=1,
            )
        )
        session.flush()

        service = TicketStateService(session)

        with pytest.raises(LeaseConflictError):
            service.claim_ticket(
                ticket.ticket_id,
                worker_id="worker-b",
                run_id="run-002",
                now=now,
            )


def test_start_run_and_renew_lease_require_same_worker():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            processing_status="leased",
            current_run_id="run-100",
            lease_owner="worker-a",
            lease_expires_at=now + timedelta(minutes=5),
            version=2,
        )
        session.add(ticket)
        session.flush()
        service = TicketStateService(session)

        started = service.start_run(
            ticket.ticket_id,
            worker_id="worker-a",
            expected_version=2,
            now=now,
        )
        assert started.processing_status == "running"
        assert started.version == 3

        renewed = service.renew_lease(
            ticket.ticket_id,
            worker_id="worker-a",
            expected_version=3,
            now=now + timedelta(minutes=1),
        )
        assert renewed.lease_expires_at == now + timedelta(minutes=6)
        assert renewed.version == 4

        with pytest.raises(LeaseConflictError):
            service.renew_lease(
                ticket.ticket_id,
                worker_id="worker-b",
                expected_version=4,
                now=now + timedelta(minutes=2),
            )


def test_fail_run_moves_ticket_to_failed_and_error_and_clears_lease():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="triaged",
            processing_status="running",
            current_run_id="run-200",
            lease_owner="worker-a",
            lease_expires_at=now + timedelta(minutes=5),
            version=5,
        )
        session.add(ticket)
        session.flush()
        service = TicketStateService(session)

        updated = service.fail_run(
            ticket.ticket_id,
            worker_id="worker-a",
            error_code="gmail_500_timeout",
            error_message="gmail returned 500",
            expected_version=5,
            now=now,
        )

        assert updated.business_status == "failed"
        assert updated.processing_status == "error"
        assert updated.last_error_code == "gmail_500_timeout"
        assert updated.last_error_message == "gmail returned 500"
        assert updated.lease_owner is None
        assert updated.lease_expires_at is None
        assert updated.version == 6


def test_requeue_failed_ticket_respects_auto_retry_limit():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="failed",
            processing_status="error",
            version=4,
        )
        session.add(ticket)
        session.flush()
        session.add(_build_run(ticket.ticket_id, trigger_type="scheduled_retry", attempt_index=1))
        session.add(_build_run(ticket.ticket_id, trigger_type="scheduled_retry", attempt_index=2))
        session.add(_build_run(ticket.ticket_id, trigger_type="scheduled_retry", attempt_index=3))
        ticket.last_error_code = "gmail_500_timeout"
        session.flush()

        service = TicketStateService(session)

        with pytest.raises(InvalidStateTransitionError):
            service.requeue_failed_ticket(
                ticket.ticket_id,
                expected_version=4,
            )


def test_requeue_failed_ticket_clears_error_and_sets_back_to_triaged_and_queued():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="failed",
            processing_status="error",
            version=2,
        )
        ticket.last_error_code = "network_timeout"
        ticket.last_error_message = "temporary network issue"
        session.add(ticket)
        session.flush()
        session.add(_build_run(ticket.ticket_id, trigger_type="scheduled_retry", attempt_index=1))
        session.flush()

        service = TicketStateService(session)
        updated = service.requeue_failed_ticket(
            ticket.ticket_id,
            expected_version=2,
            run_id="run-retry-2",
        )

        assert updated.business_status == "triaged"
        assert updated.processing_status == "queued"
        assert updated.last_error_code is None
        assert updated.last_error_message is None
        assert updated.current_run_id == "run-retry-2"
        assert updated.version == 3


def test_reclaim_expired_lease_returns_ticket_to_queue():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="triaged",
            processing_status="error",
            version=9,
            lease_owner="worker-a",
            lease_expires_at=now - timedelta(seconds=1),
        )
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        run = TicketRun(
            run_id="run-lease-expired",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="running",
            started_at=now - timedelta(minutes=5),
            attempt_index=1,
        )
        ticket.current_run_id = run.run_id
        session.add(run)
        session.flush()
        updated = service.reclaim_expired_lease(
            ticket.ticket_id,
            expected_version=9,
            now=now,
        )

        assert updated.processing_status == "queued"
        assert updated.lease_owner is None
        assert updated.lease_expires_at is None
        assert updated.version == 10
        assert session.get(TicketRun, run.run_id).status == "queued"


def test_complete_run_rejects_stale_run_after_current_run_switched():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="triaged",
            processing_status="running",
            version=4,
            current_run_id="run-new",
            lease_owner="worker-a",
            lease_expires_at=now + timedelta(minutes=5),
        )
        session.add(ticket)
        session.add(
            TicketRun(
                run_id="run-new",
                ticket_id=ticket.ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="running",
                started_at=now,
                attempt_index=1,
            )
        )
        session.flush()

        service = TicketStateService(session)
        with pytest.raises(LeaseConflictError):
            service.complete_run(
                ticket.ticket_id,
                worker_id="worker-a",
                run_id="run-old",
                business_status="draft_created",
                expected_version=4,
                now=now,
            )


def test_service_transitions_ticket_by_id_with_expected_version():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(version=4)
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        updated = service.transition_business_status(
            ticket.ticket_id,
            target_status="triaged",
            expected_version=4,
            metadata_updates={
                "primary_route": "knowledge_request",
                "routing_reason": "Knowledge route selected during triage.",
            },
        )
        session.flush()

        assert updated.ticket_id == ticket.ticket_id
        assert updated.business_status == "triaged"
        assert updated.version == 5
        assert updated.primary_route == "knowledge_request"


def test_service_raises_version_conflict_for_stale_expected_version():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(version=2)
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)

        with pytest.raises(VersionConflictError):
            service.transition_business_status(
                ticket.ticket_id,
                target_status="triaged",
                expected_version=1,
            )


def test_draft_idempotency_returns_existing_gmail_draft():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="triaged",
            processing_status="running",
        )
        session.add(ticket)
        session.flush()
        run = _build_run(ticket.ticket_id)
        session.add(run)
        session.flush()

        idempotency_key = f"draft:{ticket.ticket_id}:reply:1"
        draft = DraftArtifact(
            draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
            ticket_id=ticket.ticket_id,
            run_id=run.run_id,
            version_index=1,
            draft_type="reply",
            content_text="Draft body",
            qa_status="passed",
            gmail_draft_id="gmail-draft-1",
            idempotency_key=idempotency_key,
            created_at=datetime.now(timezone.utc),
        )
        session.add(draft)
        session.flush()

        service = TicketStateService(session)
        existing = service.ensure_draft_idempotency(
            ticket_id=ticket.ticket_id,
            draft_type=DraftType.REPLY,
            version_index=1,
        )

        assert existing.draft_id == draft.draft_id


def test_draft_idempotency_rejects_closed_ticket():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="closed",
            processing_status="completed",
        )
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        with pytest.raises(InvalidStateTransitionError):
            service.ensure_draft_idempotency(
                ticket_id=ticket.ticket_id,
                draft_type=DraftType.REPLY,
                version_index=1,
            )


def test_validate_manual_action_precondition_blocks_invalid_states():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="triaged",
            processing_status="completed",
        )
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        with pytest.raises(InvalidStateTransitionError):
            service.validate_manual_action_precondition(
                ticket.ticket_id,
                action=HumanReviewAction.APPROVE.value,
                expected_version=1,
            )


def test_apply_approve_review_moves_ticket_to_approved_and_completed():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="awaiting_human_review",
            processing_status="waiting_external",
            version=7,
        )
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        updated_ticket, review = service.apply_manual_review_action(
            ticket_id=ticket.ticket_id,
            action=HumanReviewAction.APPROVE,
            reviewer_id="reviewer-1",
            ticket_version_at_review=7,
            comment="looks good",
        )

        assert review.action == "approve"
        assert updated_ticket.business_status == "approved"
        assert updated_ticket.processing_status == "completed"
        assert updated_ticket.version == 8


def test_apply_edit_and_approve_creates_new_draft_artifact():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="awaiting_human_review",
            processing_status="waiting_external",
            version=5,
        )
        run = _build_run(ticket.ticket_id, trigger_type="human_action", attempt_index=2)
        session.add(ticket)
        session.flush()
        run.ticket_id = ticket.ticket_id
        session.add(run)
        session.flush()

        existing_draft = DraftArtifact(
            draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
            ticket_id=ticket.ticket_id,
            run_id=run.run_id,
            version_index=1,
            draft_type="reply",
            content_text="Old draft",
            qa_status="pending",
            created_at=datetime.now(timezone.utc),
        )
        session.add(existing_draft)
        session.flush()

        service = TicketStateService(session)
        updated_ticket, review = service.apply_manual_review_action(
            ticket_id=ticket.ticket_id,
            action=HumanReviewAction.EDIT_AND_APPROVE,
            reviewer_id="reviewer-2",
            ticket_version_at_review=5,
            draft_id=existing_draft.draft_id,
            comment="softened wording",
            edited_content_text="Updated customer-safe draft",
            run_id=run.run_id,
        )
        session.flush()

        drafts = session.query(DraftArtifact).filter_by(ticket_id=ticket.ticket_id).all()

        assert review.action == "edit_and_approve"
        assert updated_ticket.business_status == "approved"
        assert updated_ticket.processing_status == "completed"
        assert updated_ticket.version == 6
        assert len(drafts) == 2
        assert max(draft.version_index for draft in drafts) == 2


def test_apply_rewrite_review_requeues_ticket():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="awaiting_human_review",
            processing_status="waiting_external",
            version=8,
        )
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        updated_ticket, review = service.apply_manual_review_action(
            ticket_id=ticket.ticket_id,
            action=HumanReviewAction.REJECT_FOR_REWRITE,
            reviewer_id="reviewer-3",
            ticket_version_at_review=8,
            comment="too strong",
            rewrite_reasons=["policy_wording_too_strong"],
        )

        assert review.action == "reject_for_rewrite"
        assert review.requested_rewrite_reason == {
            "reasons": ["policy_wording_too_strong"]
        }
        assert updated_ticket.business_status == "rejected"
        assert updated_ticket.processing_status == "queued"
        assert updated_ticket.version == 9


def test_apply_escalate_review_moves_ticket_to_waiting_external():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket(
            business_status="triaged",
            processing_status="completed",
            version=4,
        )
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)
        updated_ticket, review = service.apply_manual_review_action(
            ticket_id=ticket.ticket_id,
            action=HumanReviewAction.ESCALATE,
            reviewer_id="reviewer-4",
            ticket_version_at_review=4,
            target_queue="security_support",
        )

        assert review.action == "escalate"
        assert review.target_queue == "security_support"
        assert updated_ticket.business_status == "escalated"
        assert updated_ticket.processing_status == "waiting_external"
        assert updated_ticket.version == 5


def test_processing_state_machine_rejects_invalid_transition():
    machine = TicketProcessingStateMachine()

    with pytest.raises(InvalidStateTransitionError):
        machine.assert_can_transition("queued", "completed")


def test_closed_ticket_cannot_create_new_draft_idempotency_key_when_version_invalid():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket()
        session.add(ticket)
        session.flush()

        service = TicketStateService(session)

        with pytest.raises(CoreSchemaError):
            service.build_draft_idempotency_key(
                ticket_id=ticket.ticket_id,
                draft_type="reply",
                version_index=0,
            )
