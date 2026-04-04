from __future__ import annotations

from datetime import datetime, timezone
import json

from src.orchestration.state import (
    Email,
    build_claim_projection,
    build_initial_graph_state,
    build_ticket_run_state,
    get_active_email,
    set_active_email,
)


def test_build_initial_graph_state_uses_ticket_run_shape():
    state = build_initial_graph_state()

    assert state["business_status"] == "new"
    assert state["processing_status"] == "queued"
    assert state["clarification_history"] == []
    assert state["resume_count"] == 0
    assert state["checkpoint_metadata"] == {
        "thread_id": "",
        "checkpoint_ns": "",
        "last_checkpoint_node": None,
        "last_checkpoint_at": None,
    }
    assert state["rewrite_count"] == 0
    assert state["draft_versions"] == []


def test_build_ticket_run_state_sets_active_email(sample_email_payload):
    state = build_ticket_run_state(
        ticket_id="t_001",
        run_id="run_001",
        raw_email=sample_email_payload,
    )

    assert state["ticket_id"] == "t_001"
    assert state["thread_id"] == sample_email_payload["threadId"]
    assert state["normalized_email"] == sample_email_payload["body"]
    assert state["raw_email"]["subject"] == "Pricing question"
    assert state["checkpoint_metadata"] == {
        "thread_id": "t_001",
        "checkpoint_ns": "run_001",
        "last_checkpoint_node": None,
        "last_checkpoint_at": None,
    }


def test_get_active_email_uses_raw_email(sample_email_payload):
    email = Email(**sample_email_payload)
    state = build_ticket_run_state(raw_email=email)

    assert get_active_email(state) == email

def test_set_active_email_updates_raw_email_fields(sample_email_payload):
    first = Email(**sample_email_payload)
    state = build_initial_graph_state()

    updates = set_active_email(state, first)
    assert updates["raw_email"] == first.model_dump(mode="json")
    assert updates["normalized_email"] == first.body
    assert updates["thread_id"] == first.threadId


def test_ticket_run_state_is_json_serializable_with_recovery_fields(sample_email_payload):
    state = build_ticket_run_state(
        ticket_id="t_001",
        run_id="run_001",
        raw_email=sample_email_payload,
    )
    state["clarification_history"] = [
        {
            "question": "Please share the exact error text shown in the UI.",
            "asked_at": "2026-04-03T10:00:00+08:00",
            "source": "clarify_request",
        }
    ]
    state["resume_count"] = 2
    state["checkpoint_metadata"]["last_checkpoint_node"] = "qa_review"
    state["checkpoint_metadata"]["last_checkpoint_at"] = "2026-04-03T10:01:00+08:00"

    payload = json.loads(json.dumps(state))

    assert payload["resume_count"] == 2
    assert payload["clarification_history"][0]["source"] == "clarify_request"
    assert payload["checkpoint_metadata"]["checkpoint_ns"] == "run_001"


def test_build_ticket_run_state_accepts_claim_projection_fields():
    state = build_ticket_run_state(
        ticket_id="t_001",
        run_id="run_001",
        claimed_by="worker-1",
        claimed_at="2026-04-03T10:00:00+08:00",
        lease_until="2026-04-03T10:05:00+08:00",
    )

    assert state["claimed_by"] == "worker-1"
    assert state["claimed_at"] == "2026-04-03T10:00:00+08:00"
    assert state["lease_until"] == "2026-04-03T10:05:00+08:00"


def test_build_claim_projection_uses_current_run_started_at_only():
    projection = build_claim_projection(
        lease_owner="worker-1",
        lease_expires_at=datetime(2026, 4, 3, 2, 5, tzinfo=timezone.utc),
        current_run_id="run_001",
        run_id="run_001",
        run_started_at=datetime(2026, 4, 3, 2, 0, tzinfo=timezone.utc),
    )

    assert projection == {
        "claimed_by": "worker-1",
        "claimed_at": "2026-04-03T02:00:00+00:00",
        "lease_until": "2026-04-03T02:05:00+00:00",
    }

    unrelated = build_claim_projection(
        lease_owner="worker-1",
        lease_expires_at=datetime(2026, 4, 3, 2, 5, tzinfo=timezone.utc),
        current_run_id="run_002",
        run_id="run_001",
        run_started_at=datetime(2026, 4, 3, 2, 0, tzinfo=timezone.utc),
    )

    assert unrelated["claimed_by"] == "worker-1"
    assert unrelated["lease_until"] == "2026-04-03T02:05:00+00:00"
    assert unrelated["claimed_at"] is None
