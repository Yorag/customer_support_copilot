from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

from src.contracts.core import TicketRoute, TicketTag
from src.contracts.outputs import TriageOutput
from src.llm.runtime import LlmInvocationResult
from src.prompts.loader import load_prompt_template
from src.triage import TriageContext, TriageDecision
from src.triage.policy import (
    PRIORITY_RANK,
    ROUTE_RESPONSE_STRATEGY,
    max_priority,
)


@dataclass(frozen=True)
class TriageMergeResult:
    output: TriageOutput
    guardrails_adjusted: bool
    llm_requested_escalation: bool
    llm_requested_clarification: bool
    llm_raised_priority: bool


class TriageAgentMixin:
    @property
    def triage_email(self):
        return RunnableLambda(self._invoke_triage_email_from_payload)

    def triage_email_with_rules(
        self,
        *,
        subject: str | None,
        email: str,
        context: TriageContext | None = None,
    ) -> TriageDecision:
        return self.triage_email_with_rules_detailed(
            subject=subject,
            email=email,
            context=context,
        )

    def triage_email_with_rules_detailed(
        self,
        *,
        subject: str | None,
        email: str,
        context: TriageContext | None = None,
    ) -> TriageDecision:
        triage_context = context or TriageContext()
        rule_based = self.triage_service.evaluate(
            subject=subject,
            body=email,
            context=triage_context,
        )
        try:
            llm_invocation = self.invoke_triage_email(
                subject=subject,
                email=email,
                context=triage_context,
            )
        except Exception:
            return TriageDecision(
                output=rule_based.output,
                selected_rule="fallback_rule_service",
                matched_rules=("fallback_rule_service", *rule_based.matched_rules),
                priority_reasons=rule_based.priority_reasons,
                escalation_reasons=rule_based.escalation_reasons,
                clarification_reasons=rule_based.clarification_reasons,
            )

        merge_result = self._merge_triage_outputs(
            llm_output=llm_invocation.parsed_output,
            rule_output=rule_based.output,
        )

        escalation_reasons = list(rule_based.escalation_reasons)
        if merge_result.llm_requested_escalation and not escalation_reasons:
            escalation_reasons.append("LLM triage requested escalation.")

        clarification_reasons = list(rule_based.clarification_reasons)
        if merge_result.llm_requested_clarification and not clarification_reasons:
            clarification_reasons.append("LLM triage requested additional clarification.")

        priority_reasons = list(rule_based.priority_reasons)
        if merge_result.llm_raised_priority:
            priority_reasons.append("LLM triage raised the ticket priority.")

        return TriageDecision(
            output=merge_result.output,
            selected_rule="llm_structured_output",
            matched_rules=("llm_structured_output", *rule_based.matched_rules),
            priority_reasons=tuple(priority_reasons),
            escalation_reasons=tuple(escalation_reasons),
            clarification_reasons=tuple(clarification_reasons),
            llm_invocation=llm_invocation,
        )

    def invoke_triage_email(
        self,
        *,
        subject: str | None,
        email: str,
        context: TriageContext,
    ) -> LlmInvocationResult:
        triage_prompt = load_prompt_template("triage_email.txt")
        return self._runtime.invoke_structured(
            PromptTemplate(
                template=triage_prompt,
                input_variables=[
                    "subject",
                    "email",
                    "is_high_value_customer",
                    "recent_customer_replies_72h",
                    "requires_manual_approval",
                    "qa_failure_count",
                    "knowledge_evidence_sufficient",
                ],
            ),
            schema=TriageOutput,
            inputs=self._build_triage_inputs(subject=subject, email=email, context=context),
        )

    def _merge_triage_outputs(
        self,
        *,
        llm_output: TriageOutput,
        rule_output: TriageOutput,
    ) -> TriageMergeResult:
        primary_route = llm_output.primary_route

        needs_escalation = llm_output.needs_escalation or rule_output.needs_escalation
        escalation_guardrail_applied = (
            rule_output.needs_escalation and not llm_output.needs_escalation
        )
        llm_requested_escalation = (
            llm_output.needs_escalation and not rule_output.needs_escalation
        )

        if primary_route is TicketRoute.TECHNICAL_ISSUE:
            needs_clarification = (
                llm_output.needs_clarification or rule_output.needs_clarification
            )
            clarification_guardrail_applied = (
                rule_output.needs_clarification and not llm_output.needs_clarification
            )
            llm_requested_clarification = (
                llm_output.needs_clarification and not rule_output.needs_clarification
            )
        else:
            needs_clarification = False
            clarification_guardrail_applied = False
            llm_requested_clarification = False

        merged_secondary_routes = self._merge_secondary_routes(
            primary_route=primary_route,
            llm_output=llm_output,
            rule_output=rule_output,
        )
        merged_tags = self._merge_tags(
            llm_tags=llm_output.tags,
            rule_tags=rule_output.tags,
            needs_clarification=needs_clarification,
            needs_escalation=needs_escalation,
        )

        guardrails_adjusted = any(
            (
                escalation_guardrail_applied,
                clarification_guardrail_applied,
            )
        )
        intent_confidence = (
            min(llm_output.intent_confidence, rule_output.intent_confidence)
            if guardrails_adjusted
            else llm_output.intent_confidence
        )
        priority = max_priority(llm_output.priority, rule_output.priority)
        llm_raised_priority = (
            PRIORITY_RANK[llm_output.priority] > PRIORITY_RANK[rule_output.priority]
        )
        routing_reason = llm_output.routing_reason
        if guardrails_adjusted:
            routing_reason = (
                f"{llm_output.routing_reason} Guardrails applied: "
                f"{rule_output.routing_reason}"
            )

        return TriageMergeResult(
            output=TriageOutput(
                primary_route=primary_route,
                secondary_routes=merged_secondary_routes,
                tags=merged_tags,
                response_strategy=ROUTE_RESPONSE_STRATEGY[primary_route],
                multi_intent=bool(merged_secondary_routes),
                intent_confidence=intent_confidence,
                priority=priority,
                needs_clarification=needs_clarification,
                needs_escalation=needs_escalation,
                routing_reason=routing_reason,
            ),
            guardrails_adjusted=guardrails_adjusted,
            llm_requested_escalation=llm_requested_escalation,
            llm_requested_clarification=llm_requested_clarification,
            llm_raised_priority=llm_raised_priority,
        )

    def _merge_secondary_routes(
        self,
        *,
        primary_route: TicketRoute,
        llm_output: TriageOutput,
        rule_output: TriageOutput,
    ) -> list[TicketRoute]:
        merged: list[TicketRoute] = []
        candidates = list(llm_output.secondary_routes)
        if llm_output.primary_route is not primary_route:
            candidates.append(llm_output.primary_route)
        candidates.extend(rule_output.secondary_routes)
        if rule_output.primary_route is not primary_route:
            candidates.append(rule_output.primary_route)

        for route in candidates:
            if route is primary_route or route is TicketRoute.UNRELATED or route in merged:
                continue
            merged.append(route)
            if len(merged) == 2:
                break

        return merged

    def _merge_tags(
        self,
        *,
        llm_tags: list[TicketTag],
        rule_tags: list[TicketTag],
        needs_clarification: bool,
        needs_escalation: bool,
    ) -> list[TicketTag]:
        merged: list[TicketTag] = []
        for tag in list(rule_tags) + list(llm_tags):
            if tag not in merged:
                merged.append(tag)

        required_tags: list[TicketTag] = []
        if needs_clarification:
            required_tags.append(TicketTag.NEEDS_CLARIFICATION)
        if needs_escalation:
            required_tags.append(TicketTag.NEEDS_ESCALATION)

        for tag in required_tags:
            if tag in merged:
                continue
            if len(merged) >= 5:
                removable_index = next(
                    (
                        index
                        for index in range(len(merged) - 1, -1, -1)
                        if merged[index] not in required_tags
                    ),
                    None,
                )
                if removable_index is not None:
                    merged.pop(removable_index)
            merged.append(tag)

        return merged[:5]

    def _build_triage_inputs(
        self,
        *,
        subject: str | None,
        email: str,
        context: TriageContext,
    ) -> dict[str, str | int]:
        return {
            "subject": subject or "",
            "email": email,
            "is_high_value_customer": str(context.is_high_value_customer).lower(),
            "recent_customer_replies_72h": context.recent_customer_replies_72h,
            "requires_manual_approval": str(context.requires_manual_approval).lower(),
            "qa_failure_count": context.qa_failure_count,
            "knowledge_evidence_sufficient": str(context.knowledge_evidence_sufficient).lower(),
        }

    def _invoke_triage_email_from_payload(self, payload: dict[str, Any]) -> TriageOutput:
        context = TriageContext(
            is_high_value_customer=str(
                payload.get("is_high_value_customer", "false")
            ).lower()
            == "true",
            recent_customer_replies_72h=int(payload.get("recent_customer_replies_72h", 0)),
            requires_manual_approval=str(
                payload.get("requires_manual_approval", "false")
            ).lower()
            == "true",
            qa_failure_count=int(payload.get("qa_failure_count", 0)),
            knowledge_evidence_sufficient=str(
                payload.get("knowledge_evidence_sufficient", "true")
            ).lower()
            == "true",
        )
        return self.invoke_triage_email(
            subject=payload.get("subject"),
            email=str(payload["email"]),
            context=context,
        ).parsed_output
