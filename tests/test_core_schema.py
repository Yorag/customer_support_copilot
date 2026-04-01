from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.core_schema import (
    CoreSchemaError,
    EntityIdPrefix,
    SourceChannel,
    TicketRoute,
    TicketTag,
    VersionConflictError,
    assert_expected_version,
    generate_prefixed_id,
    next_version,
    normalize_ticket_routing,
    to_api_timestamp,
    utc_now,
    validate_prefixed_id,
    validate_source_channel,
    validate_version,
)


def test_generate_prefixed_id_uses_spec_prefix_and_ulid_shape():
    ticket_id = generate_prefixed_id(EntityIdPrefix.TICKET)

    assert ticket_id.startswith("t_")
    assert validate_prefixed_id(ticket_id, EntityIdPrefix.TICKET) == ticket_id


def test_validate_prefixed_id_rejects_wrong_prefix():
    with pytest.raises(CoreSchemaError):
        validate_prefixed_id("run_01JQJQJ4D7QMWJ8C5DVBAB4M2T", EntityIdPrefix.TICKET)


def test_validate_source_channel_only_accepts_gmail():
    assert validate_source_channel("gmail") is SourceChannel.GMAIL

    with pytest.raises(CoreSchemaError):
        validate_source_channel("web_form")


def test_normalize_ticket_routing_adds_multi_intent_tag_when_needed():
    selection = normalize_ticket_routing(
        primary_route="commercial_policy_request",
        secondary_routes=["technical_issue"],
        tags=["billing_question"],
        multi_intent=True,
    )

    assert selection.source_channel is SourceChannel.GMAIL
    assert selection.primary_route is TicketRoute.COMMERCIAL_POLICY_REQUEST
    assert selection.secondary_routes == (TicketRoute.TECHNICAL_ISSUE,)
    assert selection.tags == (
        TicketTag.BILLING_QUESTION,
        TicketTag.MULTI_INTENT,
    )


def test_normalize_ticket_routing_removes_multi_intent_tag_when_false():
    selection = normalize_ticket_routing(
        tags=["multi_intent", "billing_question"],
        multi_intent=False,
    )

    assert selection.secondary_routes == ()
    assert selection.tags == (TicketTag.BILLING_QUESTION,)


def test_normalize_ticket_routing_rejects_secondary_routes_without_multi_intent():
    with pytest.raises(CoreSchemaError):
        normalize_ticket_routing(
            secondary_routes=["technical_issue"],
            multi_intent=False,
        )


def test_version_helpers_enforce_optimistic_lock_rules():
    assert validate_version(1) == 1
    assert next_version(3) == 4

    with pytest.raises(CoreSchemaError):
        validate_version(0)

    with pytest.raises(VersionConflictError):
        assert_expected_version(expected=2, actual=3, entity="ticket")


def test_time_helpers_keep_timezone_information():
    current_time = utc_now()

    assert current_time.tzinfo is not None
    assert current_time.utcoffset() == timezone.utc.utcoffset(current_time)

    api_timestamp = to_api_timestamp(datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc))
    assert api_timestamp == "2026-04-01T10:30:00+00:00"
