from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.prompts import PromptTemplate

from src.contracts.outputs import KnowledgePolicyOutput, RiskLevel
from src.llm.runtime import LlmInvocationResult
from src.prompts.loader import load_prompt_template


_RISK_LEVEL_RANK = {
    RiskLevel.low: 0,
    RiskLevel.medium: 1,
    RiskLevel.high: 2,
}


@dataclass(frozen=True)
class KnowledgePolicyAgentResult:
    output: KnowledgePolicyOutput
    llm_invocation: LlmInvocationResult | None
    fallback_used: bool
    guardrails_adjusted: bool


class KnowledgePolicyAgentMixin:
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
        return self.knowledge_policy_agent_detailed(
            primary_route=primary_route,
            response_strategy=response_strategy,
            normalized_email=normalized_email,
            knowledge_answers=knowledge_answers,
            policy_notes=policy_notes,
            knowledge_confidence=knowledge_confidence,
            needs_escalation=needs_escalation,
        ).output

    def knowledge_policy_agent_detailed(
        self,
        *,
        primary_route: str,
        response_strategy: str,
        normalized_email: str,
        knowledge_answers: list[dict[str, str]] | None = None,
        policy_notes: str = "",
        knowledge_confidence: float | None = None,
        needs_escalation: bool = False,
    ) -> KnowledgePolicyAgentResult:
        deterministic_output = self._build_deterministic_knowledge_policy_output(
            primary_route=primary_route,
            response_strategy=response_strategy,
            normalized_email=normalized_email,
            knowledge_answers=knowledge_answers,
            policy_notes=policy_notes,
            knowledge_confidence=knowledge_confidence,
            needs_escalation=needs_escalation,
        )
        try:
            llm_invocation = self.invoke_knowledge_policy_agent(
                primary_route=primary_route,
                response_strategy=response_strategy,
                normalized_email=normalized_email,
                knowledge_answers=knowledge_answers,
                policy_notes=policy_notes,
                knowledge_confidence=knowledge_confidence,
                needs_escalation=needs_escalation,
            )
        except Exception:
            return KnowledgePolicyAgentResult(
                output=deterministic_output,
                llm_invocation=None,
                fallback_used=True,
                guardrails_adjusted=False,
            )

        merged_output = self._merge_knowledge_policy_outputs(
            llm_output=llm_invocation.parsed_output,
            deterministic_output=deterministic_output,
        )
        return KnowledgePolicyAgentResult(
            output=merged_output,
            llm_invocation=llm_invocation,
            fallback_used=False,
            guardrails_adjusted=(
                merged_output.model_dump(mode="json")
                != llm_invocation.parsed_output.model_dump(mode="json")
            ),
        )

    def invoke_knowledge_policy_agent(
        self,
        *,
        primary_route: str,
        response_strategy: str,
        normalized_email: str,
        knowledge_answers: list[dict[str, str]] | None = None,
        policy_notes: str = "",
        knowledge_confidence: float | None = None,
        needs_escalation: bool = False,
    ) -> LlmInvocationResult:
        prompt_template = load_prompt_template("knowledge_policy_agent.txt")
        return self._runtime.invoke_structured(
            PromptTemplate(
                template=prompt_template,
                input_variables=[
                    "primary_route",
                    "response_strategy",
                    "normalized_email",
                    "knowledge_answers_json",
                    "policy_notes",
                    "knowledge_confidence",
                    "needs_escalation",
                ],
            ),
            schema=KnowledgePolicyOutput,
            inputs={
                "primary_route": primary_route,
                "response_strategy": response_strategy,
                "normalized_email": normalized_email,
                "knowledge_answers_json": json.dumps(
                    knowledge_answers or [],
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                "policy_notes": policy_notes,
                "knowledge_confidence": (
                    "" if knowledge_confidence is None else str(knowledge_confidence)
                ),
                "needs_escalation": str(needs_escalation).lower(),
            },
        )

    def _build_deterministic_knowledge_policy_output(
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
        raw_answers = knowledge_answers or []
        answers = _filter_substantive_answers(raw_answers)
        retrieval_hit = len(answers) > 0
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
            knowledge_summary = (
                "No external knowledge lookup is required for feedback acknowledgement."
            )
            citations = []
        elif primary_route == "unrelated":
            knowledge_summary = (
                "The message is unrelated to supported customer support scope."
            )
            citations = []
        elif primary_route == "technical_issue":
            knowledge_summary = (
                "Use the reported diagnostics and request any missing troubleshooting "
                "details before claiming a fix."
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
            retrieval_hit=retrieval_hit,
        )

    def _merge_knowledge_policy_outputs(
        self,
        *,
        llm_output: KnowledgePolicyOutput,
        deterministic_output: KnowledgePolicyOutput,
    ) -> KnowledgePolicyOutput:
        llm_risk_rank = _RISK_LEVEL_RANK[llm_output.risk_level]
        deterministic_risk_rank = _RISK_LEVEL_RANK[deterministic_output.risk_level]
        merged_risk_level = (
            llm_output.risk_level
            if llm_risk_rank >= deterministic_risk_rank
            else deterministic_output.risk_level
        )

        allowed_actions = _merge_unique_strings(
            llm_output.allowed_actions,
            deterministic_output.allowed_actions,
        )
        disallowed_actions = _merge_unique_strings(
            deterministic_output.disallowed_actions,
            llm_output.disallowed_actions,
        )

        return KnowledgePolicyOutput(
            queries=deterministic_output.queries or llm_output.queries,
            knowledge_summary=(
                llm_output.knowledge_summary.strip()
                or deterministic_output.knowledge_summary
            ),
            citations=deterministic_output.citations or llm_output.citations,
            knowledge_confidence=min(
                llm_output.knowledge_confidence,
                deterministic_output.knowledge_confidence,
            ),
            risk_level=merged_risk_level,
            allowed_actions=allowed_actions,
            disallowed_actions=disallowed_actions,
            policy_notes=llm_output.policy_notes.strip() or deterministic_output.policy_notes,
            retrieval_hit=deterministic_output.retrieval_hit,
        )


def knowledge_policy_agent(*args, **kwargs) -> KnowledgePolicyOutput:
    return KnowledgePolicyAgentMixin().knowledge_policy_agent(*args, **kwargs)


def _merge_unique_strings(*sequences: list[str]) -> list[str]:
    merged: list[str] = []
    for sequence in sequences:
        for item in sequence:
            normalized = item.strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


_NO_KNOWLEDGE_PATTERNS = (
    "i don't know",
    "i do not know",
    "no relevant information",
    "unable to determine",
    "not enough information",
)


def _filter_substantive_answers(
    answers: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Return only answers that contain substantive content.

    RAG may return answers like "I don't know." when the vector store has no
    matching chunks.  These should not count as successful retrieval hits.
    """
    substantive: list[dict[str, str]] = []
    for item in answers:
        answer_text = (item.get("answer") or "").strip().lower()
        if not answer_text:
            continue
        if any(pattern in answer_text for pattern in _NO_KNOWLEDGE_PATTERNS):
            continue
        substantive.append(item)
    return substantive


__all__ = [
    "KnowledgePolicyAgentMixin",
    "KnowledgePolicyAgentResult",
    "knowledge_policy_agent",
]
