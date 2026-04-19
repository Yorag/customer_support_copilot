from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from src.bootstrap.container import ServiceContainer
from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.db.models import Ticket, TicketRun
from src.evaluation import RuleBasedResponseQualityBaseline, validate_judge_output
from src.llm.runtime import (
    TOKEN_SOURCE_ESTIMATED,
    TOKEN_SOURCE_PROVIDER_ACTUAL,
    TOKEN_SOURCE_PROVIDER_MAPPED,
    TOKEN_SOURCE_UNAVAILABLE,
    extract_usage,
)
from src.telemetry.trace import TraceRecorder
from src.workers.runner import TicketRunner


def test_validate_judge_output_requires_fixed_schema():
    result = validate_judge_output(
        {
            "relevance": 5,
            "correctness": 4,
            "intent_alignment": 4,
            "clarity": 4,
            "reason": "schema ok",
        }
    )
    assert result.overall_score == 4.25

    with pytest.raises(ValueError):
        validate_judge_output(
            {
                "relevance": 5,
                "correctness": 4,
                "intent_alignment": 4,
                "clarity": 4,
            }
        )


def test_eval_samples_cover_minimum_v1_surface():
    sample_path = (
        Path(__file__).resolve().parent.parent
        / "evals"
        / "samples"
        / "customer_support_eval_zh.jsonl"
    )
    rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 53
    assert len({row["sample_id"] for row in rows}) == 53
    assert {
        row["scenario_type"] for row in rows
    } == {
        "knowledge_supported",
        "knowledge_gap",
        "technical_issue_clarification",
        "technical_issue_detailed",
        "commercial_policy_high_risk",
        "commercial_policy_standard",
        "feedback_intake",
        "unrelated",
        "multi_intent",
    }


def test_extract_usage_prefers_provider_actual():
    usage = extract_usage(
        AIMessage(
            content="ok",
            usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        )
    )

    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 4
    assert usage.total_tokens == 14
    assert usage.token_source == TOKEN_SOURCE_PROVIDER_ACTUAL


def test_extract_usage_falls_back_to_provider_mapped():
    usage = extract_usage(
        AIMessage(
            content="ok",
            response_metadata={"token_usage": {"prompt_tokens": 8, "completion_tokens": 3}},
        )
    )

    assert usage.prompt_tokens == 8
    assert usage.completion_tokens == 3
    assert usage.total_tokens == 11
    assert usage.token_source == TOKEN_SOURCE_PROVIDER_MAPPED


def test_extract_usage_recomputes_inconsistent_total_tokens():
    usage = extract_usage(
        AIMessage(
            content="ok",
            usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 999},
        )
    )

    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 4
    assert usage.total_tokens == 14
    assert usage.token_source == TOKEN_SOURCE_PROVIDER_ACTUAL


def test_extract_usage_falls_back_to_estimated():
    usage = extract_usage(
        None,
        prompt_texts=["hello world"],
        completion_text="reply text",
    )

    assert usage.prompt_tokens is not None
    assert usage.completion_tokens is not None
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
    assert usage.token_source == TOKEN_SOURCE_ESTIMATED


def test_extract_usage_returns_unavailable_without_inputs():
    usage = extract_usage(None, prompt_texts=[], completion_text="")

    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.total_tokens is None
    assert usage.token_source == TOKEN_SOURCE_UNAVAILABLE


def test_rule_based_response_quality_baseline_is_available_only_as_explicit_baseline():
    baseline = RuleBasedResponseQualityBaseline()

    result = baseline.evaluate(
        email_subject="Need refund policy clarification",
        email_body="Can you confirm whether duplicate charges are refundable?",
        draft_text="Hello,\n\nWe will handle this request according to the applicable policy.\n\nBest regards",
        evidence_summary="policy evidence available",
        policy_summary="Refund handling must stay within policy.",
        primary_route="commercial_policy_request",
        final_action="handoff_to_human",
    )

    assert result["overall_score"] >= 1.0
    assert set(result["subscores"]) == {
        "relevance",
        "correctness",
        "intent_alignment",
        "clarity",
    }


class _FakeTraceEventsRepository:
    def __init__(self) -> None:
        self._events = []

    def add(self, event) -> None:
        self._events.append(event)

    def list_by_run(self, run_id: str):
        return [event for event in self._events if event.run_id == run_id]


class _FakeRepositories:
    def __init__(self) -> None:
        self.trace_events = _FakeTraceEventsRepository()


class _FakeTraceExporter:
    def __init__(self) -> None:
        self.root_calls = 0
        self.child_calls = 0
        self.finalize_calls = 0

    def create_root_run(self, **kwargs):
        self.root_calls += 1
        return {"kind": "root"}

    def create_child_run(self, **kwargs):
        self.child_calls += 1
        return {"kind": "child"}

    def finalize_run(self, **kwargs) -> None:
        self.finalize_calls += 1


def test_build_resource_metrics_tracks_token_source_mix():
    ticket = Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="thread-001",
        source_message_id="msg-001",
        gmail_thread_id="gmail-thread-001",
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject="Need help with login",
        business_status="new",
        processing_status="queued",
        priority="high",
        secondary_routes=[],
        tags=[],
        multi_intent=False,
        needs_clarification=False,
        needs_escalation=False,
        risk_reasons=[],
    )
    started_at = datetime.now(timezone.utc)
    run = TicketRun(
        run_id=generate_prefixed_id(EntityIdPrefix.RUN),
        ticket_id=ticket.ticket_id,
        trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
        trigger_type="manual_api",
        status="running",
        started_at=started_at,
        attempt_index=1,
    )
    recorder = TraceRecorder(repositories=_FakeRepositories(), langsmith_client=None)

    recorder.record_llm_call(
        run=run,
        ticket=ticket,
        event_name="triage_llm",
        node_name="triage",
        model="gpt-4o-mini",
        provider="openai-compatible",
        start_time=started_at,
        end_time=started_at,
        prompt_tokens=10,
        completion_tokens=4,
        token_source=TOKEN_SOURCE_PROVIDER_ACTUAL,
    )
    recorder.record_llm_call(
        run=run,
        ticket=ticket,
        event_name="judge_llm",
        node_name="qa_review",
        model="gpt-4o-mini",
        provider="openai-compatible",
        start_time=started_at,
        end_time=started_at,
        prompt_tokens=6,
        completion_tokens=2,
        token_source=TOKEN_SOURCE_ESTIMATED,
    )
    recorder.record_llm_call(
        run=run,
        ticket=ticket,
        event_name="fallback_llm",
        node_name="draft_reply",
        model="gpt-4o-mini",
        provider="openai-compatible",
        start_time=started_at,
        end_time=started_at,
        prompt_tokens=None,
        completion_tokens=None,
        token_source=TOKEN_SOURCE_UNAVAILABLE,
    )

    metrics = recorder.build_resource_metrics(run=run)

    assert metrics["prompt_tokens_total"] == 16
    assert metrics["completion_tokens_total"] == 6
    assert metrics["total_tokens"] == 22
    assert metrics["llm_call_count"] == 3
    assert metrics["actual_token_call_count"] == 1
    assert metrics["estimated_token_call_count"] == 1
    assert metrics["unavailable_token_call_count"] == 1
    assert metrics["token_coverage_ratio"] == 0.333


def test_trace_recorder_accepts_legacy_langsmith_client_argument():
    ticket = Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="thread-legacy",
        source_message_id="msg-legacy",
        gmail_thread_id="gmail-thread-legacy",
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject="Legacy trace exporter",
        business_status="new",
        processing_status="queued",
        priority="high",
        secondary_routes=[],
        tags=[],
        multi_intent=False,
        needs_clarification=False,
        needs_escalation=False,
        risk_reasons=[],
    )
    started_at = datetime.now(timezone.utc)
    run = TicketRun(
        run_id=generate_prefixed_id(EntityIdPrefix.RUN),
        ticket_id=ticket.ticket_id,
        trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
        trigger_type="manual_api",
        status="running",
        started_at=started_at,
        attempt_index=1,
    )
    exporter = _FakeTraceExporter()
    recorder = TraceRecorder(repositories=_FakeRepositories(), langsmith_client=exporter)

    recorder.start_run(
        ticket=ticket,
        run=run,
        inputs={"ticket_id": ticket.ticket_id},
    )
    recorder.record_decision(
        run=run,
        ticket=ticket,
        event_name="triage_result",
        node_name="triage",
        metadata={
            "primary_route": "knowledge_request",
            "secondary_routes": [],
            "response_strategy": "answer",
            "needs_clarification": False,
            "needs_escalation": False,
            "final_action": "create_draft",
        },
    )
    run.ended_at = started_at
    recorder.finalize_run(run=run, ticket=ticket)

    assert exporter.root_calls == 1
    assert exporter.child_calls == 1
    assert exporter.finalize_calls == 1


def test_service_container_exposes_trace_exporter_singleton():
    exporter = _FakeTraceExporter()
    container = ServiceContainer(trace_exporter_factory=lambda: exporter)

    assert container.trace_exporter is exporter
    assert container.trace_exporter is exporter


def test_ticket_runner_uses_trace_exporter_from_container():
    exporter = _FakeTraceExporter()
    container = ServiceContainer(
        trace_exporter_factory=lambda: exporter,
        response_quality_judge_factory=lambda: object(),
    )
    runner = TicketRunner(
        session=object(),
        repositories=_FakeRepositories(),
        container=container,
    )

    assert runner.trace_recorder._trace_exporter is exporter
