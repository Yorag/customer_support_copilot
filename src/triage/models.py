from __future__ import annotations

from dataclasses import dataclass

from src.llm.runtime import LlmInvocationResult

from src.contracts.core import TicketRoute
from src.contracts.outputs import TriageOutput


@dataclass(frozen=True)
class TriageContext:
    is_high_value_customer: bool = False
    recent_customer_replies_72h: int = 0
    requires_manual_approval: bool = False
    qa_failure_count: int = 0
    knowledge_evidence_sufficient: bool = True


@dataclass(frozen=True)
class TriageDecision:
    output: TriageOutput
    selected_rule: str
    matched_rules: tuple[str, ...]
    priority_reasons: tuple[str, ...]
    escalation_reasons: tuple[str, ...]
    hard_escalation_reasons: tuple[str, ...] = ()
    soft_escalation_reasons: tuple[str, ...] = ()
    clarification_reasons: tuple[str, ...]  = ()
    llm_invocation: LlmInvocationResult | None = None


@dataclass(frozen=True)
class _RouteMatch:
    rule_id: str
    route: TicketRoute
    score: int
    reasons: tuple[str, ...]
