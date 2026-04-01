from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .core_schema import (
    ResponseStrategy,
    TicketPriority,
    TicketRoute,
    TicketTag,
)
from .structure_outputs import TriageOutput


_ROUTE_PRIORITY = {
    TicketRoute.COMMERCIAL_POLICY_REQUEST: 0,
    TicketRoute.TECHNICAL_ISSUE: 1,
    TicketRoute.KNOWLEDGE_REQUEST: 2,
    TicketRoute.FEEDBACK_INTAKE: 3,
    TicketRoute.UNRELATED: 4,
}

_ROUTE_RESPONSE_STRATEGY = {
    TicketRoute.KNOWLEDGE_REQUEST: ResponseStrategy.ANSWER,
    TicketRoute.TECHNICAL_ISSUE: ResponseStrategy.TROUBLESHOOTING,
    TicketRoute.COMMERCIAL_POLICY_REQUEST: ResponseStrategy.POLICY_CONSTRAINED,
    TicketRoute.FEEDBACK_INTAKE: ResponseStrategy.ACKNOWLEDGEMENT,
    TicketRoute.UNRELATED: ResponseStrategy.ACKNOWLEDGEMENT,
}

_PRIORITY_ORDER = [
    TicketPriority.LOW,
    TicketPriority.MEDIUM,
    TicketPriority.HIGH,
    TicketPriority.CRITICAL,
]


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
    clarification_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _RouteMatch:
    rule_id: str
    route: TicketRoute
    score: int
    reasons: tuple[str, ...]


class TriageDecisionService:
    def evaluate(
        self,
        *,
        subject: str | None,
        body: str,
        context: TriageContext | None = None,
    ) -> TriageDecision:
        triage_context = context or TriageContext()
        normalized_text = self._normalize_text(subject=subject, body=body)
        route_matches = self._match_routes(normalized_text)
        matched_routes = [match.route for match in route_matches]

        primary_match = self._select_primary_match(route_matches)
        secondary_matches = self._select_secondary_matches(
            route_matches=route_matches,
            primary_route=primary_match.route,
        )
        multi_intent = bool(secondary_matches)

        tags = self._build_tags(normalized_text, primary_match.route)
        clarification_reasons = self._collect_clarification_reasons(
            normalized_text,
            primary_match.route,
        )
        needs_clarification = bool(clarification_reasons)

        confidence = self._compute_confidence(
            route_matches=route_matches,
            primary_match=primary_match,
            multi_intent=multi_intent,
        )

        escalation_reasons = self._collect_escalation_reasons(
            normalized_text,
            context=triage_context,
            confidence=confidence,
            matched_routes=matched_routes,
            tags=tags,
        )
        needs_escalation = bool(escalation_reasons)

        priority, priority_reasons = self._compute_priority(
            normalized_text,
            context=triage_context,
            primary_route=primary_match.route,
            tags=tags,
        )

        routing_reason = self._build_routing_reason(
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
            response_strategy=_ROUTE_RESPONSE_STRATEGY[primary_match.route],
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
            clarification_reasons=clarification_reasons,
        )

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
        return sorted(
            route_matches,
            key=lambda match: (
                _ROUTE_PRIORITY[match.route],
                -match.score,
            ),
        )[0]

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
        secondary_matches.sort(
            key=lambda match: (
                _ROUTE_PRIORITY[match.route],
                -match.score,
            )
        )
        return secondary_matches[:2]

    def _match_commercial_policy_request(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        billing_keywords = (
            "bill",
            "billing",
            "invoice",
            "charge",
            "charged",
            "payment",
            "pricing",
            "subscription",
            "plan",
            "账单",
            "计费",
            "收费",
            "扣费",
            "套餐",
            "订阅",
        )
        refund_keywords = (
            "refund",
            "refunds",
            "reimburse",
            "credit back",
            "chargeback",
            "退款",
            "退费",
            "退回",
            "撤销扣款",
        )
        constrained_policy_keywords = (
            "sla",
            "compensation",
            "contract",
            "legal",
            "policy",
            "terms",
            "agreement",
            "补偿",
            "合同",
            "法律",
            "条款",
            "政策",
            "承诺边界",
        )
        cancellation_keywords = (
            "cancel subscription",
            "cancel my subscription",
            "cancel plan",
            "取消订阅",
            "取消套餐",
            "取消服务",
        )

        if _contains_any(text, billing_keywords):
            score += 2
            reasons.append("The email discusses billing, charging, or subscription details.")
        if _contains_any(text, refund_keywords):
            score += 2
            reasons.append("The customer explicitly requests a refund or charge reversal.")
        if _contains_any(text, constrained_policy_keywords):
            score += 2
            reasons.append("The request touches SLA, compensation, legal, contract, or policy constraints.")
        if _contains_any(text, cancellation_keywords):
            score += 1
            reasons.append("The customer asks for cancellation-related account action.")

        if score == 0:
            return None

        return _RouteMatch(
            rule_id="R3",
            route=TicketRoute.COMMERCIAL_POLICY_REQUEST,
            score=score,
            reasons=tuple(reasons),
        )

    def _match_technical_issue(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        error_keywords = (
            "error",
            "errors",
            "failed",
            "failure",
            "failing",
            "bug",
            "issue",
            "broken",
            "not working",
            "doesn't work",
            "cannot",
            "can't",
            "unable",
            "unavailable",
            "timeout",
            "timed out",
            "exception",
            "login failed",
            "报错",
            "失败",
            "异常",
            "无法",
            "不能",
            "不可用",
            "超时",
            "出错",
        )
        attempt_keywords = (
            "tried",
            "i tried",
            "configured",
            "set up",
            "setup",
            "followed the docs",
            "followed your guide",
            "after i",
            "when i",
            "按文档",
            "按照文档",
            "配置了",
            "升级套餐时",
            "我点击",
            "我尝试",
            "我配置",
        )

        if _contains_any(text, error_keywords):
            score += 2
            reasons.append("The customer reports an operational failure, error, or unavailable behavior.")
        if _contains_any(text, attempt_keywords):
            score += 1
            reasons.append("The customer describes an attempted action or setup before the failure.")

        if score < 2:
            return None

        return _RouteMatch(
            rule_id="R2",
            route=TicketRoute.TECHNICAL_ISSUE,
            score=score,
            reasons=tuple(reasons),
        )

    def _match_knowledge_request(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        question_keywords = (
            "how to",
            "how do i",
            "can i",
            "does it support",
            "do you support",
            "is it possible",
            "what is",
            "where can i",
            "支持吗",
            "怎么用",
            "如何",
            "是否支持",
            "说明",
            "能力边界",
            "配置说明",
        )
        capability_keywords = (
            "feature",
            "features",
            "capability",
            "capabilities",
            "support",
            "sso",
            "integration",
            "api",
            "workspace",
            "功能",
            "能力",
            "集成",
            "接口",
            "文档",
            "documentation",
            "docs",
            "guide",
        )

        has_explicit_knowledge_phrase = _contains_any(text, question_keywords)
        has_capability_signal = _contains_any(text, capability_keywords)

        if has_explicit_knowledge_phrase:
            score += 2
            reasons.append("The customer asks how a feature works, whether it is supported, or how to configure it.")
        if has_capability_signal and (
            has_explicit_knowledge_phrase or "?" in text or "？" in text
        ):
            score += 1
            reasons.append("The email focuses on product capability or configuration information.")

        if score < 2:
            return None

        return _RouteMatch(
            rule_id="R1",
            route=TicketRoute.KNOWLEDGE_REQUEST,
            score=score,
            reasons=tuple(reasons),
        )

    def _match_feedback_intake(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        suggestion_keywords = (
            "feature request",
            "suggest",
            "suggestion",
            "please add",
            "i wish",
            "feedback",
            "建议",
            "希望增加",
            "功能建议",
            "反馈",
        )
        complaint_keywords = (
            "frustrating",
            "disappointed",
            "bad experience",
            "poor experience",
            "complaint",
            "annoying",
            "不好用",
            "不满",
            "抱怨",
            "投诉",
            "体验很差",
        )

        if _contains_any(text, suggestion_keywords):
            score += 1
            reasons.append("The customer proposes product improvements or general feedback.")
        if _contains_any(text, complaint_keywords):
            score += 1
            reasons.append("The customer expresses dissatisfaction with the product experience.")

        if score == 0:
            return None

        return _RouteMatch(
            rule_id="R4",
            route=TicketRoute.FEEDBACK_INTAKE,
            score=score,
            reasons=tuple(reasons),
        )

    def _match_unrelated(self, text: str) -> _RouteMatch | None:
        reasons: list[str] = []
        score = 0

        unrelated_keywords = (
            "seo",
            "backlink",
            "partnership",
            "sponsorship",
            "recruiting",
            "hiring",
            "job opportunity",
            "sales pitch",
            "marketing service",
            "商务合作",
            "招聘",
            "推广",
            "外链",
            "海外 seo",
        )

        if _contains_any(text, unrelated_keywords):
            score += 2
            reasons.append("The email looks like outreach unrelated to customer support.")

        if score == 0:
            return None

        return _RouteMatch(
            rule_id="R5",
            route=TicketRoute.UNRELATED,
            score=score,
            reasons=tuple(reasons),
        )

    def _build_tags(self, text: str, primary_route: TicketRoute) -> list[TicketTag]:
        tags: list[TicketTag] = []

        if _contains_any(
            text,
            (
                "feature request",
                "please add",
                "i wish",
                "希望增加",
                "功能建议",
                "新增功能",
            ),
        ):
            tags.append(TicketTag.FEATURE_REQUEST)

        if _contains_any(
            text,
            (
                "frustrating",
                "disappointed",
                "complaint",
                "annoying",
                "bad experience",
                "不好用",
                "不满",
                "投诉",
                "多扣费",
            ),
        ):
            tags.append(TicketTag.COMPLAINT)

        if primary_route is TicketRoute.FEEDBACK_INTAKE and TicketTag.FEATURE_REQUEST not in tags:
            tags.append(TicketTag.GENERAL_FEEDBACK)

        if _contains_any(
            text,
            (
                "bill",
                "billing",
                "invoice",
                "charge",
                "charged",
                "payment",
                "账单",
                "计费",
                "收费",
                "扣费",
                "多扣费",
                "重复扣费",
            ),
        ):
            tags.append(TicketTag.BILLING_QUESTION)

        if _contains_any(
            text,
            (
                "refund",
                "refunds",
                "chargeback",
                "退款",
                "退费",
                "撤销扣款",
            ),
        ):
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
        if not _contains_any(
            text,
            (
                "steps to reproduce",
                "step 1",
                "step 2",
                "after i",
                "when i",
                "i clicked",
                "i configured",
                "configured",
                "followed",
                "i tried",
                "步骤",
                "我点击",
                "我配置",
                "我尝试",
                "然后",
            ),
        ):
            reasons.append("Missing reproduction steps.")
        if not _contains_any(
            text,
            (
                "error",
                "failed",
                "failure",
                "cannot",
                "can't",
                "unable",
                "timeout",
                "exception",
                "报错",
                "失败",
                "异常",
                "无法",
                "不能",
                "超时",
            ),
        ):
            reasons.append("Missing a concrete error or observed failure.")
        if not _contains_any(
            text,
            (
                "expected",
                "instead",
                "but",
                "should",
                "supposed to",
                "预期",
                "实际",
                "本应",
                "结果",
            ),
        ):
            reasons.append("Missing expected-versus-actual comparison.")
        if not _contains_any(
            text,
            (
                "tenant",
                "workspace",
                "project",
                "account",
                "environment",
                "browser",
                "region",
                "org",
                "租户",
                "工作区",
                "项目",
                "账号",
                "环境",
                "浏览器",
                "组织",
            ),
        ):
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
    ) -> tuple[str, ...]:
        reasons: list[str] = []

        if TicketTag.REFUND_REQUEST in tags:
            reasons.append("Refund handling requires manual policy review.")
        if _contains_any(
            text,
            (
                "duplicate charge",
                "charged twice",
                "charged me twice",
                "重复扣费",
                "多扣费",
            ),
        ):
            reasons.append("The case involves disputed or duplicate charges.")
        if _contains_any(
            text,
            (
                "sla",
                "compensation",
                "security incident",
                "security breach",
                "data loss",
                "legal",
                "contract",
                "补偿",
                "安全事故",
                "数据丢失",
                "法律",
                "合同",
            ),
        ):
            reasons.append("The request is high-risk because it involves SLA, compensation, security, data loss, legal, or contract concerns.")
        if (
            TicketRoute.KNOWLEDGE_REQUEST in matched_routes
            and not context.knowledge_evidence_sufficient
        ):
            reasons.append("Knowledge evidence is insufficient for a conclusive answer.")
        if confidence < 0.60:
            reasons.append("Routing confidence is below 0.60.")
        if context.qa_failure_count >= 2:
            reasons.append("QA has already failed twice for this case.")
        if context.requires_manual_approval:
            reasons.append("Customer history requires manual approval.")

        return tuple(reasons)

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

        if _contains_any(
            text,
            (
                "security incident",
                "security breach",
                "data loss",
                "legal",
                "contract",
                "sla",
                "refund amount",
                "安全事故",
                "数据丢失",
                "法律",
                "合同",
                "退款金额",
            ),
        ):
            priority = TicketPriority.CRITICAL
            reasons.append("Critical risk terms require critical priority.")
            return priority, tuple(reasons)

        if _contains_any(
            text,
            (
                "production down",
                "prod down",
                "outage",
                "service unavailable",
                "生产不可用",
                "线上不可用",
            ),
        ):
            priority = _raise_priority(priority)
            reasons.append("Production unavailability raises the priority by one level.")
        if _contains_any(
            text,
            (
                "data loss",
                "lost data",
                "数据丢失",
                "数据没了",
            ),
        ):
            priority = _raise_priority(priority)
            reasons.append("Data loss raises the priority by one level.")
        if context.is_high_value_customer:
            priority = _raise_priority(priority)
            reasons.append("High-value customer context raises the priority by one level.")
        if context.recent_customer_replies_72h >= 2:
            priority = _raise_priority(priority)
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


def _raise_priority(priority: TicketPriority) -> TicketPriority:
    index = _PRIORITY_ORDER.index(priority)
    if index == len(_PRIORITY_ORDER) - 1:
        return priority
    return _PRIORITY_ORDER[index + 1]
