from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

from .llm import build_chat_model
from .prompts import *
from .core_schema import TicketRoute, TicketTag
from .structure_outputs import (
    CategorizeEmailOutput,
    DraftingOutput,
    KnowledgePolicyOutput,
    ProofReaderOutput,
    QaHandoffOutput,
    RAGQueriesOutput,
    RiskLevel,
    TriageOutput,
    WriterOutput,
)
from .triage import TriageContext, TriageDecision, TriageDecisionService
from .triage_policy import (
    PRIORITY_RANK,
    ROUTE_PRIORITY,
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


class Agents:
    def __init__(self, *, triage_service: TriageDecisionService | None = None):
        self.triage_service = triage_service or TriageDecisionService()

    @cached_property
    def _llm(self):
        return build_chat_model(temperature=0.1)

    @cached_property
    def categorize_email(self):
        email_category_prompt = PromptTemplate(
            template=CATEGORIZE_EMAIL_PROMPT,
            input_variables=["email"],
        )
        return email_category_prompt | self._llm.with_structured_output(
            CategorizeEmailOutput
        )

    @cached_property
    def triage_email(self):
        triage_prompt = PromptTemplate(
            template=TRIAGE_EMAIL_PROMPT,
            input_variables=[
                "subject",
                "email",
                "is_high_value_customer",
                "recent_customer_replies_72h",
                "requires_manual_approval",
                "qa_failure_count",
                "knowledge_evidence_sufficient",
            ],
        )
        return triage_prompt | self._llm.with_structured_output(TriageOutput)

    @cached_property
    def design_rag_queries(self):
        generate_query_prompt = PromptTemplate(
            template=GENERATE_RAG_QUERIES_PROMPT,
            input_variables=["email"],
        )
        return generate_query_prompt | self._llm.with_structured_output(
            RAGQueriesOutput
        )

    @cached_property
    def email_writer(self):
        writer_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EMAIL_WRITER_PROMPT),
                MessagesPlaceholder("history"),
                ("human", "{email_information}"),
            ]
        )
        return writer_prompt | self._llm.with_structured_output(WriterOutput)

    @cached_property
    def email_proofreader(self):
        proofreader_prompt = PromptTemplate(
            template=EMAIL_PROOFREADER_PROMPT,
            input_variables=["initial_email", "generated_email"],
        )
        return proofreader_prompt | self._llm.with_structured_output(
            ProofReaderOutput
        )

    def triage_email_with_rules(
        self,
        *,
        subject: str | None,
        email: str,
        context: TriageContext | None = None,
    ):
        triage_context = context or TriageContext()
        rule_based = self.triage_service.evaluate(
            subject=subject,
            body=email,
            context=triage_context,
        )
        try:
            llm_output = self.triage_email.invoke(
                {
                    "subject": subject or "",
                    "email": email,
                    "is_high_value_customer": str(triage_context.is_high_value_customer).lower(),
                    "recent_customer_replies_72h": triage_context.recent_customer_replies_72h,
                    "requires_manual_approval": str(triage_context.requires_manual_approval).lower(),
                    "qa_failure_count": triage_context.qa_failure_count,
                    "knowledge_evidence_sufficient": str(triage_context.knowledge_evidence_sufficient).lower(),
                }
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
            llm_output=llm_output,
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
            selected_rule=(
                rule_based.selected_rule
                if merge_result.guardrails_adjusted
                else "llm_structured_output"
            ),
            matched_rules=("llm_structured_output", *rule_based.matched_rules),
            priority_reasons=tuple(priority_reasons),
            escalation_reasons=tuple(escalation_reasons),
            clarification_reasons=tuple(clarification_reasons),
        )

    def _merge_triage_outputs(
        self,
        *,
        llm_output: TriageOutput,
        rule_output: TriageOutput,
    ) -> TriageMergeResult:
        primary_route = llm_output.primary_route
        route_guardrail_applied = False
        if ROUTE_PRIORITY[primary_route] > ROUTE_PRIORITY[rule_output.primary_route]:
            primary_route = rule_output.primary_route
            route_guardrail_applied = True

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
                route_guardrail_applied,
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
            if tag in merged:
                continue
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

    def knowledge_policy_agent(
        self,
        *,
        primary_route: str,
        response_strategy: str,
        normalized_email: str,
        knowledge_answers: list[dict[str, str]] | None = None,
        policy_notes: str = "",
        knowledge_confidence: float | None = None,
        needs_escalation: bool = False,
    ) -> KnowledgePolicyOutput:
        answers = knowledge_answers or []
        if primary_route == "knowledge_request":
            allowed_actions = ["answer_question"]
            disallowed_actions = ["promise_refund", "invent_features"]
        elif primary_route == "technical_issue":
            allowed_actions = ["provide_troubleshooting", "request_diagnostics"]
            disallowed_actions = ["claim_issue_fixed_without_evidence"]
        elif primary_route == "commercial_policy_request":
            allowed_actions = ["cite_policy", "set_expectations"]
            disallowed_actions = ["promise_refund", "promise_compensation"]
        elif primary_route == "feedback_intake":
            allowed_actions = ["acknowledge_feedback", "summarize_request"]
            disallowed_actions = ["promise_roadmap_commitment"]
        else:
            allowed_actions = ["acknowledge_scope"]
            disallowed_actions = ["fabricate_support_scope"]

        inferred_confidence = knowledge_confidence
        if inferred_confidence is None:
            if primary_route in {"feedback_intake", "unrelated"}:
                inferred_confidence = 1.0
            elif answers:
                inferred_confidence = 0.9
            elif primary_route == "technical_issue":
                inferred_confidence = 0.65
            else:
                inferred_confidence = 0.55

        risk_level = RiskLevel.low
        if needs_escalation or primary_route == "commercial_policy_request":
            risk_level = RiskLevel.high
        elif primary_route == "technical_issue":
            risk_level = RiskLevel.medium

        if answers:
            knowledge_summary = "\n\n".join(
                f"{item['question']}\n{item['answer']}" for item in answers
            )
            citations = [
                {"title": item["question"], "snippet": item["answer"]}
                for item in answers
            ]
        elif primary_route == "feedback_intake":
            knowledge_summary = "No external knowledge lookup is required for feedback acknowledgement."
            citations = []
        elif primary_route == "unrelated":
            knowledge_summary = "The message is unrelated to supported customer support scope."
            citations = []
        elif primary_route == "technical_issue":
            knowledge_summary = (
                "Use the reported diagnostics and request any missing troubleshooting details before claiming a fix."
            )
            citations = []
        else:
            knowledge_summary = "No conclusive knowledge evidence was retrieved."
            citations = []

        return KnowledgePolicyOutput(
            queries=[item["question"] for item in answers],
            knowledge_summary=knowledge_summary,
            citations=citations,
            knowledge_confidence=inferred_confidence,
            risk_level=risk_level,
            allowed_actions=allowed_actions,
            disallowed_actions=disallowed_actions,
            policy_notes=policy_notes or "No additional policy constraints.",
        )

    def drafting_agent(
        self,
        *,
        customer_email: str,
        subject: str,
        primary_route: str,
        response_strategy: str,
        normalized_email: str,
        knowledge_summary: str,
        policy_notes: str,
        rewrite_guidance: list[str] | None = None,
    ) -> DraftingOutput:
        guidance_text = ""
        if rewrite_guidance:
            guidance_text = "\n\nRewrite guidance:\n- " + "\n- ".join(rewrite_guidance)

        greeting = "Hello,"
        closing = "\n\nBest regards"

        if primary_route == "knowledge_request":
            body = (
                "Thanks for your question. Based on the available product information, here is the most relevant guidance:\n\n"
                f"{knowledge_summary or 'We are reviewing the relevant capability details.'}"
            )
            rationale = "Answer mode uses retrieved product knowledge and avoids unsupported claims."
        elif primary_route == "technical_issue":
            body = (
                "We reviewed the issue details you shared and are treating this as a technical problem.\n\n"
                f"{knowledge_summary or 'We will continue troubleshooting based on the reported symptoms.'}"
            )
            rationale = "Troubleshooting mode keeps the reply factual and grounded in the reported diagnostics."
        elif primary_route == "commercial_policy_request":
            body = (
                "We received your billing or policy-related request and will handle it within the applicable policy boundaries.\n\n"
                f"{policy_notes}"
            )
            rationale = "Policy-constrained drafting sets expectations without making unsupported commitments."
        elif primary_route == "feedback_intake":
            body = (
                "Thank you for sharing your feedback. We have recorded it for the team and will use it to inform follow-up work where appropriate."
            )
            rationale = "Acknowledgement mode confirms receipt without implying roadmap commitments."
        else:
            body = (
                "We received your message, but it does not appear to match the supported customer support scope for this workflow."
            )
            rationale = "Out-of-scope drafting stays concise and avoids inventing unsupported assistance."

        draft_text = f"{greeting}\n\n{body}{guidance_text}{closing}"
        return DraftingOutput(
            draft_text=draft_text,
            draft_rationale=rationale,
            applied_response_strategy=response_strategy,
        )

    def qa_handoff_agent(
        self,
        *,
        primary_route: str,
        draft_text: str,
        knowledge_confidence: float,
        needs_escalation: bool,
        rewrite_count: int,
        policy_notes: str,
    ) -> QaHandoffOutput:
        quality_scores = {
            "relevance": 4.2,
            "correctness": 4.2,
            "intent_alignment": 4.2,
            "clarity": 4.2,
        }

        if needs_escalation:
            return QaHandoffOutput(
                approved=False,
                issues=["risk_requires_human_review"],
                rewrite_guidance=[],
                quality_scores=quality_scores,
                escalate=True,
                reason="Risk signals require human review before a customer-facing draft can proceed.",
                human_handoff_summary=(
                    f"Route={primary_route}; customer-facing draft withheld because manual review is required."
                ),
            )

        if knowledge_confidence < 0.6 and primary_route != "unrelated":
            return QaHandoffOutput(
                approved=False,
                issues=["knowledge_evidence_insufficient"],
                rewrite_guidance=[],
                quality_scores=quality_scores,
                escalate=True,
                reason="Knowledge confidence is too low for an automated reply.",
                human_handoff_summary=(
                    f"Route={primary_route}; insufficient evidence for a safe automated response."
                ),
            )

        if rewrite_count >= 2:
            return QaHandoffOutput(
                approved=False,
                issues=["qa_retry_limit_reached"],
                rewrite_guidance=[],
                quality_scores=quality_scores,
                escalate=True,
                reason="QA retry limit reached; send to human review instead of another rewrite.",
                human_handoff_summary=(
                    f"Route={primary_route}; QA failed multiple times and requires manual handling."
                ),
            )

        if len(draft_text.strip()) < 40:
            return QaHandoffOutput(
                approved=False,
                issues=["draft_too_short"],
                rewrite_guidance=["Expand the response so it addresses the customer request directly."],
                quality_scores=quality_scores,
                escalate=False,
                reason="Draft is too short to be customer-ready.",
                human_handoff_summary=None,
            )

        if primary_route == "commercial_policy_request" and "policy" not in (
            draft_text.lower() + " " + policy_notes.lower()
        ):
            return QaHandoffOutput(
                approved=False,
                issues=["missing_policy_boundary"],
                rewrite_guidance=["Mention that the request will be handled according to the applicable policy."],
                quality_scores=quality_scores,
                escalate=False,
                reason="Commercial policy replies must explicitly keep the response within policy boundaries.",
                human_handoff_summary=None,
            )

        return QaHandoffOutput(
            approved=True,
            issues=[],
            rewrite_guidance=[],
            quality_scores=quality_scores,
            escalate=False,
            reason="Draft satisfies the deterministic V1 QA checks.",
            human_handoff_summary=None,
        )
