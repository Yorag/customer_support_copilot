from __future__ import annotations

from src.contracts.outputs import TriageOutput
from .models import TriageContext, TriageDecision
from .policy import ROUTE_RESPONSE_STRATEGY
from .rules import TriageRules


class TriageDecisionService:
    def __init__(self, *, rules: TriageRules | None = None):
        self._rules = rules or TriageRules()

    def evaluate(
        self,
        *,
        subject: str | None,
        body: str,
        context: TriageContext | None = None,
    ) -> TriageDecision:
        triage_context = context or TriageContext()
        normalized_text = self._rules._normalize_text(subject=subject, body=body)
        route_matches = self._rules._match_routes(normalized_text)
        matched_routes = [match.route for match in route_matches]

        primary_match = self._rules._select_primary_match(route_matches)
        secondary_matches = self._rules._select_secondary_matches(
            route_matches=route_matches,
            primary_route=primary_match.route,
        )
        multi_intent = bool(secondary_matches)

        tags = self._rules._build_tags(normalized_text, primary_match.route)
        clarification_reasons = self._rules._collect_clarification_reasons(
            normalized_text,
            primary_match.route,
        )
        needs_clarification = bool(clarification_reasons)

        confidence = self._rules._compute_confidence(
            route_matches=route_matches,
            primary_match=primary_match,
            multi_intent=multi_intent,
        )

        hard_escalation_reasons, soft_escalation_reasons = (
            self._rules._collect_escalation_reasons(
                normalized_text,
                context=triage_context,
                confidence=confidence,
                matched_routes=matched_routes,
                tags=tags,
            )
        )
        escalation_reasons = hard_escalation_reasons + soft_escalation_reasons
        needs_escalation = bool(escalation_reasons)

        priority, priority_reasons = self._rules._compute_priority(
            normalized_text,
            context=triage_context,
            primary_route=primary_match.route,
            tags=tags,
        )

        routing_reason = self._rules._build_routing_reason(
            primary_match=primary_match,
            secondary_matches=secondary_matches,
            clarification_reasons=clarification_reasons,
            escalation_reasons=escalation_reasons,
            priority=priority,
        )

        output = TriageOutput(
            primary_route=primary_match.route,
            secondary_routes=[match.route for match in secondary_matches],
            tags=tags,
            response_strategy=ROUTE_RESPONSE_STRATEGY[primary_match.route],
            multi_intent=multi_intent,
            intent_confidence=confidence,
            priority=priority,
            needs_clarification=needs_clarification,
            needs_escalation=needs_escalation,
            routing_reason=routing_reason,
        )

        return TriageDecision(
            output=output,
            selected_rule=primary_match.rule_id,
            matched_rules=tuple(match.rule_id for match in route_matches),
            priority_reasons=priority_reasons,
            escalation_reasons=escalation_reasons,
            hard_escalation_reasons=hard_escalation_reasons,
            soft_escalation_reasons=soft_escalation_reasons,
            clarification_reasons=clarification_reasons,
        )
