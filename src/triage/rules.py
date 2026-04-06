from __future__ import annotations

from typing import Iterable

from src.contracts.core import TicketPriority, TicketRoute, TicketTag
from .models import TriageContext, _RouteMatch
from .policy import ROUTE_PRIORITY, bump_priority
from .signals import (
    BILLING_QUESTION_KEYWORDS,
    CLARIFICATION_ENVIRONMENT_KEYWORDS,
    CLARIFICATION_ERROR_KEYWORDS,
    CLARIFICATION_EXPECTED_ACTUAL_KEYWORDS,
    CLARIFICATION_REPRODUCTION_KEYWORDS,
    COMMERCIAL_POLICY_SIGNALS,
    COMPLAINT_KEYWORDS,
    ESCALATION_DISPUTED_CHARGE_KEYWORDS,
    ESCALATION_HIGH_RISK_KEYWORDS,
    FEATURE_REQUEST_KEYWORDS,
    FEEDBACK_INTAKE_SIGNALS,
    KNOWLEDGE_REQUEST_CAPABILITY_KEYWORDS,
    KNOWLEDGE_REQUEST_QUESTION_KEYWORDS,
    PRIORITY_CRITICAL_KEYWORDS,
    PRIORITY_DATA_LOSS_KEYWORDS,
    PRIORITY_PRODUCTION_DOWN_KEYWORDS,
    REFUND_REQUEST_KEYWORDS,
    TECHNICAL_ISSUE_SIGNALS,
    UNRELATED_KEYWORDS,
)


class TriageRules:
    def _normalize_text(self, *, subject: str | None, body: str) -> str:
        return f"{subject or ''}\n{body}".strip().lower()

    def _match_routes(self, text: str) -> list[_RouteMatch]:
        matches = [
            self._match_commercial_policy_request(text),
            self._match_technical_issue(text),
            self._match_knowledge_request(text),
            self._match_feedback_intake(text),
            self._match_unrelated(text),
        ]
        filtered_matches = [match for match in matches if match is not None]
        if filtered_matches:
            return filtered_matches

        return [
            _RouteMatch(
                rule_id="R5",
                route=TicketRoute.UNRELATED,
                score=1,
                reasons=("No clear product-support intent was detected.",),
            )
        ]

    def _select_primary_match(self, route_matches: list[_RouteMatch]) -> _RouteMatch:
        return min(route_matches, key=_route_match_sort_key)

    def _select_secondary_matches(
        self,
        *,
        route_matches: list[_RouteMatch],
        primary_route: TicketRoute,
    ) -> list[_RouteMatch]:
        secondary_matches = [
            match
            for match in route_matches
            if match.route is not primary_route and match.route is not TicketRoute.UNRELATED
        ]
        return sorted(secondary_matches, key=_route_match_sort_key)[:2]

    def _match_commercial_policy_request(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        for phrases, points, reason in COMMERCIAL_POLICY_SIGNALS:
            score += _score_signal(text, reasons, phrases, points, reason)

        return _build_route_match(
            rule_id="R3",
            route=TicketRoute.COMMERCIAL_POLICY_REQUEST,
            score=score,
            reasons=reasons,
        )

    def _match_technical_issue(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        for phrases, points, reason in TECHNICAL_ISSUE_SIGNALS:
            score += _score_signal(text, reasons, phrases, points, reason)

        return _build_route_match(
            rule_id="R2",
            route=TicketRoute.TECHNICAL_ISSUE,
            score=score,
            reasons=reasons,
            min_score=2,
        )

    def _match_knowledge_request(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        has_explicit_knowledge_phrase = _contains_any(
            text,
            KNOWLEDGE_REQUEST_QUESTION_KEYWORDS,
        )
        has_capability_signal = _contains_any(
            text,
            KNOWLEDGE_REQUEST_CAPABILITY_KEYWORDS,
        )

        if has_explicit_knowledge_phrase:
            score += 2
            reasons.append("The customer asks how a feature works, whether it is supported, or how to configure it.")
        if has_capability_signal and (
            has_explicit_knowledge_phrase or "?" in text or "？" in text
        ):
            score += 1
            reasons.append("The email focuses on product capability or configuration information.")

        return _build_route_match(
            rule_id="R1",
            route=TicketRoute.KNOWLEDGE_REQUEST,
            score=score,
            reasons=reasons,
            min_score=2,
        )

    def _match_feedback_intake(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        for phrases, points, reason in FEEDBACK_INTAKE_SIGNALS:
            score += _score_signal(text, reasons, phrases, points, reason)

        return _build_route_match(
            rule_id="R4",
            route=TicketRoute.FEEDBACK_INTAKE,
            score=score,
            reasons=reasons,
        )

    def _match_unrelated(self, text: str) -> _RouteMatch | None:
        reasons = ["The email looks like outreach unrelated to customer support."]

        return _build_route_match(
            rule_id="R5",
            route=TicketRoute.UNRELATED,
            score=2 if _contains_any(text, UNRELATED_KEYWORDS) else 0,
            reasons=reasons,
        )

    def _build_tags(self, text: str, primary_route: TicketRoute) -> list[TicketTag]:
        tags: list[TicketTag] = []

        if _contains_any(text, FEATURE_REQUEST_KEYWORDS):
            tags.append(TicketTag.FEATURE_REQUEST)

        if _contains_any(text, COMPLAINT_KEYWORDS):
            tags.append(TicketTag.COMPLAINT)

        if primary_route is TicketRoute.FEEDBACK_INTAKE and TicketTag.FEATURE_REQUEST not in tags:
            tags.append(TicketTag.GENERAL_FEEDBACK)

        if _contains_any(text, BILLING_QUESTION_KEYWORDS):
            tags.append(TicketTag.BILLING_QUESTION)

        if _contains_any(text, REFUND_REQUEST_KEYWORDS):
            tags.append(TicketTag.REFUND_REQUEST)

        return _dedupe_tags(tags)

    def _collect_clarification_reasons(
        self,
        text: str,
        primary_route: TicketRoute,
    ) -> tuple[str, ...]:
        if primary_route is not TicketRoute.TECHNICAL_ISSUE:
            return ()

        reasons: list[str] = []
        if not _contains_any(text, CLARIFICATION_REPRODUCTION_KEYWORDS):
            reasons.append("Missing reproduction steps.")
        if not _contains_any(text, CLARIFICATION_ERROR_KEYWORDS):
            reasons.append("Missing a concrete error or observed failure.")
        if not _contains_any(text, CLARIFICATION_EXPECTED_ACTUAL_KEYWORDS):
            reasons.append("Missing expected-versus-actual comparison.")
        if not _contains_any(text, CLARIFICATION_ENVIRONMENT_KEYWORDS):
            reasons.append("Missing environment, account, tenant, or project details.")
        return tuple(reasons)

    def _compute_confidence(
        self,
        *,
        route_matches: list[_RouteMatch],
        primary_match: _RouteMatch,
        multi_intent: bool,
    ) -> float:
        if len(route_matches) == 1 and primary_match.score <= 1:
            return 0.55

        confidence = 0.9 if primary_match.score >= 3 else 0.78
        if multi_intent:
            confidence -= 0.05
        if len(route_matches) >= 3:
            confidence -= 0.05
        if primary_match.score <= 1:
            confidence -= 0.15
        return round(max(0.0, min(confidence, 1.0)), 3)

    def _collect_escalation_reasons(
        self,
        text: str,
        *,
        context: TriageContext,
        confidence: float,
        matched_routes: list[TicketRoute],
        tags: list[TicketTag],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return ``(hard_reasons, soft_reasons)``.

        *Hard* reasons are non-negotiable guardrails (e.g. refund, disputed
        charges, SLA) – these **must** escalate regardless of LLM opinion.

        *Soft* reasons are heuristic signals (low confidence, insufficient
        knowledge evidence) – the LLM is better at judging these, so the
        merge layer may let the LLM override them.
        """
        hard: list[str] = []
        soft: list[str] = []

        if TicketTag.REFUND_REQUEST in tags:
            hard.append("Refund handling requires manual policy review.")
        if _contains_any(text, ESCALATION_DISPUTED_CHARGE_KEYWORDS):
            hard.append("The case involves disputed or duplicate charges.")
        if _contains_any(text, ESCALATION_HIGH_RISK_KEYWORDS):
            hard.append("The request is high-risk because it involves SLA, compensation, security, data loss, legal, or contract concerns.")
        if context.qa_failure_count >= 2:
            hard.append("QA has already failed twice for this case.")
        if context.requires_manual_approval:
            hard.append("Customer history requires manual approval.")

        if (
            TicketRoute.KNOWLEDGE_REQUEST in matched_routes
            and not context.knowledge_evidence_sufficient
        ):
            soft.append("Knowledge evidence is insufficient for a conclusive answer.")
        if confidence < 0.60:
            soft.append("Routing confidence is below 0.60.")

        return tuple(hard), tuple(soft)

    def _compute_priority(
        self,
        text: str,
        *,
        context: TriageContext,
        primary_route: TicketRoute,
        tags: list[TicketTag],
    ) -> tuple[TicketPriority, tuple[str, ...]]:
        reasons: list[str] = []

        if primary_route is TicketRoute.UNRELATED:
            priority = TicketPriority.LOW
            reasons.append("Unrelated content defaults to low priority.")
        elif primary_route in {
            TicketRoute.TECHNICAL_ISSUE,
            TicketRoute.COMMERCIAL_POLICY_REQUEST,
        } or TicketTag.COMPLAINT in tags:
            priority = TicketPriority.HIGH
            reasons.append("Technical issues, billing cases, and complaints default to high priority.")
        else:
            priority = TicketPriority.MEDIUM
            reasons.append("General knowledge requests and feedback default to medium priority.")

        if _contains_any(text, PRIORITY_CRITICAL_KEYWORDS):
            priority = TicketPriority.CRITICAL
            reasons.append("Critical risk terms require critical priority.")
            return priority, tuple(reasons)

        if _contains_any(text, PRIORITY_PRODUCTION_DOWN_KEYWORDS):
            priority = bump_priority(priority)
            reasons.append("Production unavailability raises the priority by one level.")
        if _contains_any(text, PRIORITY_DATA_LOSS_KEYWORDS):
            priority = bump_priority(priority)
            reasons.append("Data loss raises the priority by one level.")
        if context.is_high_value_customer:
            priority = bump_priority(priority)
            reasons.append("High-value customer context raises the priority by one level.")
        if context.recent_customer_replies_72h >= 2:
            priority = bump_priority(priority)
            reasons.append("Repeated replies within 72 hours raise the priority by one level.")

        return priority, tuple(reasons)

    def _build_routing_reason(
        self,
        *,
        primary_match: _RouteMatch,
        secondary_matches: list[_RouteMatch],
        clarification_reasons: tuple[str, ...],
        escalation_reasons: tuple[str, ...],
        priority: TicketPriority,
    ) -> str:
        segments = [primary_match.reasons[0]]

        if secondary_matches:
            secondary_routes = ", ".join(match.route.value for match in secondary_matches)
            segments.append(f"Secondary routes retained: {secondary_routes}.")
        if clarification_reasons:
            segments.append("Clarification is required because diagnostic details are incomplete.")
        if escalation_reasons:
            segments.append(f"Escalation is required: {escalation_reasons[0]}")
        segments.append(f"Priority is set to {priority.value}.")
        return " ".join(segments)


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _dedupe_tags(tags: list[TicketTag]) -> list[TicketTag]:
    deduped: list[TicketTag] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped


def _route_match_sort_key(match: _RouteMatch) -> tuple[int, int]:
    return (ROUTE_PRIORITY[match.route], -match.score)


def _score_signal(
    text: str,
    reasons: list[str],
    phrases: Iterable[str],
    points: int,
    reason: str,
) -> int:
    if not _contains_any(text, phrases):
        return 0

    reasons.append(reason)
    return points


def _build_route_match(
    *,
    rule_id: str,
    route: TicketRoute,
    score: int,
    reasons: list[str],
    min_score: int = 1,
) -> _RouteMatch | None:
    if score < min_score:
        return None

    return _RouteMatch(
        rule_id=rule_id,
        route=route,
        score=score,
        reasons=tuple(reasons),
    )
