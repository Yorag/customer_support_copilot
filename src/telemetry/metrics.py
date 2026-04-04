from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any, Iterable

from src.contracts.core import TraceEventType, utc_now
from src.db.models import TicketRun, TraceEvent
from src.llm.runtime import (
    TOKEN_SOURCE_ESTIMATED,
    TOKEN_SOURCE_PROVIDER_ACTUAL,
    TOKEN_SOURCE_PROVIDER_MAPPED,
    TOKEN_SOURCE_UNAVAILABLE,
    _as_int as _normalized_token_count,
    _estimate_token_usage as estimate_token_usage,
)


def duration_ms(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() * 1000))


def build_latency_metrics(
    *,
    run: TicketRun,
    events: Iterable[TraceEvent],
) -> dict[str, Any]:
    ordered_events = list(events)
    end_to_end_ms = duration_ms(run.started_at, run.ended_at or utc_now())

    node_events = [
        event for event in ordered_events if event.event_type == TraceEventType.NODE.value
    ]
    llm_events = [
        event for event in ordered_events if event.event_type == TraceEventType.LLM_CALL.value
    ]
    tool_events = [
        event for event in ordered_events if event.event_type == TraceEventType.TOOL_CALL.value
    ]

    node_groups: dict[str, list[int]] = {}
    for event in node_events:
        if event.event_name == "run_ticket":
            continue
        if event.latency_ms is None:
            continue
        key = event.node_name or event.event_name
        node_groups.setdefault(key, []).append(event.latency_ms)

    node_latencies = {
        key: round(mean(values), 3)
        for key, values in sorted(node_groups.items())
        if values
    }
    slowest_node = None
    if node_latencies:
        slowest_node = max(node_latencies.items(), key=lambda item: item[1])[0]

    slowest_call = None
    for event in ordered_events:
        if event.latency_ms is None:
            continue
        if slowest_call is None or event.latency_ms > slowest_call["latency_ms"]:
            slowest_call = {
                "event_name": event.event_name,
                "latency_ms": event.latency_ms,
            }

    return {
        "end_to_end_ms": end_to_end_ms,
        "slowest_node": slowest_node,
        "slowest_call": slowest_call,
        "node_latencies": node_latencies,
        "llm_call_latencies": {
            event.event_name: event.latency_ms
            for event in llm_events
            if event.latency_ms is not None
        },
        "tool_call_latencies": {
            event.event_name: event.latency_ms
            for event in tool_events
            if event.latency_ms is not None
        },
    }


def build_resource_metrics(*, events: Iterable[TraceEvent]) -> dict[str, Any]:
    ordered_events = list(events)
    llm_events = [
        event for event in ordered_events if event.event_type == TraceEventType.LLM_CALL.value
    ]
    tool_events = [
        event for event in ordered_events if event.event_type == TraceEventType.TOOL_CALL.value
    ]

    prompt_tokens_total = 0
    completion_tokens_total = 0
    actual_token_call_count = 0
    estimated_token_call_count = 0
    unavailable_token_call_count = 0
    for event in llm_events:
        metadata = event.event_metadata or {}
        prompt_tokens = _normalized_token_count(metadata.get("prompt_tokens"))
        completion_tokens = _normalized_token_count(metadata.get("completion_tokens"))
        if prompt_tokens is not None:
            prompt_tokens_total += prompt_tokens
        if completion_tokens is not None:
            completion_tokens_total += completion_tokens
        token_source = metadata.get("token_source")
        if token_source in {
            TOKEN_SOURCE_PROVIDER_ACTUAL,
            TOKEN_SOURCE_PROVIDER_MAPPED,
        }:
            actual_token_call_count += 1
        elif token_source == TOKEN_SOURCE_ESTIMATED:
            estimated_token_call_count += 1
        elif token_source == TOKEN_SOURCE_UNAVAILABLE:
            unavailable_token_call_count += 1

    return {
        "prompt_tokens_total": prompt_tokens_total,
        "completion_tokens_total": completion_tokens_total,
        "total_tokens": prompt_tokens_total + completion_tokens_total,
        "llm_call_count": len(llm_events),
        "tool_call_count": len(tool_events),
        "actual_token_call_count": actual_token_call_count,
        "estimated_token_call_count": estimated_token_call_count,
        "unavailable_token_call_count": unavailable_token_call_count,
        "token_coverage_ratio": round(actual_token_call_count / len(llm_events), 3)
        if llm_events
        else 0.0,
    }


__all__ = [
    "duration_ms",
    "build_latency_metrics",
    "build_resource_metrics",
    "estimate_token_usage",
]
