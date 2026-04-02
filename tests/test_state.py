from __future__ import annotations

from src.state import (
    Email,
    build_initial_graph_state,
    build_ticket_run_state,
    get_active_email,
    pop_pending_email,
    set_active_email,
)


def test_build_initial_graph_state_uses_ticket_run_shape():
    state = build_initial_graph_state()

    assert state["business_status"] == "new"
    assert state["processing_status"] == "queued"
    assert state["pending_emails"] == []
    assert state["emails"] == []
    assert state["rewrite_count"] == 0
    assert state["draft_versions"] == []


def test_build_ticket_run_state_sets_active_email_and_pending_queue(sample_email_payload):
    state = build_ticket_run_state(
        ticket_id="t_001",
        pending_emails=[sample_email_payload],
    )

    assert state["ticket_id"] == "t_001"
    assert state["thread_id"] == sample_email_payload["threadId"]
    assert state["normalized_email"] == sample_email_payload["body"]
    assert state["raw_email"].subject == "Pricing question"
    assert state["emails"][0].messageId == sample_email_payload["messageId"]


def test_get_active_email_prefers_raw_email_then_pending_queue(sample_email_payload):
    email = Email(**sample_email_payload)
    state = build_ticket_run_state(raw_email=email)

    assert get_active_email(state) == email

    updated = build_initial_graph_state()
    updated["pending_emails"] = [email]
    updated["emails"] = [email]

    assert get_active_email(updated) == email


def test_set_active_email_and_pop_pending_email_keep_queue_in_sync(sample_email_payload):
    first = Email(**sample_email_payload)
    second = Email(
        **{
            **sample_email_payload,
            "id": "email_002",
            "threadId": "thread_002",
            "messageId": "<message_002@example.com>",
            "subject": "Refund request",
        }
    )
    state = build_ticket_run_state(pending_emails=[first, second])

    popped = pop_pending_email(state)
    assert popped == second
    assert state["pending_emails"] == [first]

    updates = set_active_email(state, first)
    assert updates["raw_email"] == first
    assert updates["normalized_email"] == first.body
    assert updates["thread_id"] == first.threadId
