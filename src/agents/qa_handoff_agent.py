from __future__ import annotations

from dataclasses import dataclass

from langchain_core.prompts import PromptTemplate

from src.contracts.outputs import QaHandoffOutput
from src.llm.runtime import LlmInvocationResult
from src.prompts.loader import load_prompt_template


@dataclass(frozen=True)
class QaHandoffAgentResult:
    output: QaHandoffOutput
    llm_invocation: LlmInvocationResult | None
    fallback_used: bool
    guardrails_adjusted: bool


class QaHandoffAgentMixin:
    def qa_handoff_agent(
        self,
        *,
        primary_route: str,
        draft_text: str,
        knowledge_confidence: float,
        needs_escalation: bool,
        rewrite_count: int,
        policy_notes: str,
        retrieval_hit: bool = True,
    ) -> QaHandoffOutput:
        return self.qa_handoff_agent_detailed(
            primary_route=primary_route,
            draft_text=draft_text,
            knowledge_confidence=knowledge_confidence,
            needs_escalation=needs_escalation,
            rewrite_count=rewrite_count,
            policy_notes=policy_notes,
            retrieval_hit=retrieval_hit,
        ).output

    def qa_handoff_agent_detailed(
        self,
        *,
        primary_route: str,
        draft_text: str,
        knowledge_confidence: float,
        needs_escalation: bool,
        rewrite_count: int,
        policy_notes: str,
        retrieval_hit: bool = True,
    ) -> QaHandoffAgentResult:
        deterministic_output = self._build_deterministic_qa_handoff_output(
            primary_route=primary_route,
            draft_text=draft_text,
            knowledge_confidence=knowledge_confidence,
            needs_escalation=needs_escalation,
            rewrite_count=rewrite_count,
            policy_notes=policy_notes,
            retrieval_hit=retrieval_hit,
        )
        try:
            llm_invocation = self.invoke_qa_handoff_agent(
                primary_route=primary_route,
                draft_text=draft_text,
                knowledge_confidence=knowledge_confidence,
                needs_escalation=needs_escalation,
                rewrite_count=rewrite_count,
                policy_notes=policy_notes,
            )
        except Exception:
            return QaHandoffAgentResult(
                output=deterministic_output,
                llm_invocation=None,
                fallback_used=True,
                guardrails_adjusted=False,
            )

        merged_output = self._merge_qa_handoff_outputs(
            llm_output=llm_invocation.parsed_output,
            deterministic_output=deterministic_output,
        )
        return QaHandoffAgentResult(
            output=merged_output,
            llm_invocation=llm_invocation,
            fallback_used=False,
            guardrails_adjusted=(
                merged_output.model_dump(mode="json")
                != llm_invocation.parsed_output.model_dump(mode="json")
            ),
        )

    def invoke_qa_handoff_agent(
        self,
        *,
        primary_route: str,
        draft_text: str,
        knowledge_confidence: float,
        needs_escalation: bool,
        rewrite_count: int,
        policy_notes: str,
    ) -> LlmInvocationResult:
        prompt_template = load_prompt_template("qa_handoff_agent.txt")
        return self._runtime.invoke_structured(
            PromptTemplate(
                template=prompt_template,
                input_variables=[
                    "primary_route",
                    "draft_text",
                    "knowledge_confidence",
                    "needs_escalation",
                    "rewrite_count",
                    "policy_notes",
                ],
            ),
            schema=QaHandoffOutput,
            inputs={
                "primary_route": primary_route,
                "draft_text": draft_text,
                "knowledge_confidence": str(knowledge_confidence),
                "needs_escalation": str(needs_escalation).lower(),
                "rewrite_count": str(rewrite_count),
                "policy_notes": policy_notes,
            },
        )

    def _build_deterministic_qa_handoff_output(
        self,
        *,
        primary_route: str,
        draft_text: str,
        knowledge_confidence: float,
        needs_escalation: bool,
        rewrite_count: int,
        policy_notes: str,
        retrieval_hit: bool = True,
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
                reason=(
                    "Risk signals require human review before a customer-facing "
                    "draft can proceed."
                ),
                human_handoff_summary=(
                    f"Route={primary_route}; customer-facing draft withheld "
                    "because manual review is required."
                ),
            )

        if knowledge_confidence < 0.6 and retrieval_hit and primary_route != "unrelated":
            return QaHandoffOutput(
                approved=False,
                issues=["knowledge_evidence_insufficient"],
                rewrite_guidance=[],
                quality_scores=quality_scores,
                escalate=True,
                reason="Knowledge confidence is too low for an automated reply.",
                human_handoff_summary=(
                    f"Route={primary_route}; insufficient evidence for a safe "
                    "automated response."
                ),
            )

        if knowledge_confidence < 0.6 and not retrieval_hit and primary_route != "unrelated":
            return QaHandoffOutput(
                approved=False,
                issues=["knowledge_retrieval_miss"],
                rewrite_guidance=[
                    "No matching knowledge was retrieved. Draft a conservative "
                    "response that acknowledges the question, states the known "
                    "boundary clearly, and avoids fabricating capabilities.",
                ],
                quality_scores=quality_scores,
                escalate=False,
                reason=(
                    "RAG returned no substantive evidence. Allow one rewrite "
                    "with conservative guidance instead of immediate escalation."
                ),
                human_handoff_summary=None,
            )

        if rewrite_count >= 3:
            return QaHandoffOutput(
                approved=False,
                issues=["qa_retry_limit_reached"],
                rewrite_guidance=[],
                quality_scores=quality_scores,
                escalate=True,
                reason=(
                    "QA retry limit reached; send to human review instead of "
                    "another rewrite."
                ),
                human_handoff_summary=(
                    f"Route={primary_route}; QA failed multiple times and "
                    "requires manual handling."
                ),
            )

        if len(draft_text.strip()) < 40:
            return QaHandoffOutput(
                approved=False,
                issues=["draft_too_short"],
                rewrite_guidance=[
                    "Expand the response so it addresses the customer request directly."
                ],
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
                rewrite_guidance=[
                    "Mention that the request will be handled according to the applicable policy."
                ],
                quality_scores=quality_scores,
                escalate=False,
                reason=(
                    "Commercial policy replies must explicitly keep the response "
                    "within policy boundaries."
                ),
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

    def _merge_qa_handoff_outputs(
        self,
        *,
        llm_output: QaHandoffOutput,
        deterministic_output: QaHandoffOutput,
    ) -> QaHandoffOutput:
        if deterministic_output.escalate:
            return deterministic_output

        issues = _merge_unique_strings(deterministic_output.issues, llm_output.issues)
        rewrite_guidance = _merge_unique_strings(
            deterministic_output.rewrite_guidance,
            llm_output.rewrite_guidance,
        )
        quality_scores = llm_output.quality_scores or deterministic_output.quality_scores

        approved = llm_output.approved and deterministic_output.approved
        escalate = bool(llm_output.escalate)
        if escalate:
            approved = False
            rewrite_guidance = []

        reason = llm_output.reason.strip() or deterministic_output.reason
        if not deterministic_output.approved and llm_output.approved:
            reason = f"{reason} Guardrail applied: {deterministic_output.reason}"

        return QaHandoffOutput(
            approved=approved,
            issues=issues,
            rewrite_guidance=rewrite_guidance,
            quality_scores=quality_scores,
            escalate=escalate,
            reason=reason,
            human_handoff_summary=(
                llm_output.human_handoff_summary
                if escalate
                else None
            ),
        )


def qa_handoff_agent(*args, **kwargs) -> QaHandoffOutput:
    return QaHandoffAgentMixin().qa_handoff_agent(*args, **kwargs)


def _merge_unique_strings(*sequences: list[str]) -> list[str]:
    merged: list[str] = []
    for sequence in sequences:
        for item in sequence:
            normalized = item.strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


__all__ = ["QaHandoffAgentMixin", "QaHandoffAgentResult", "qa_handoff_agent"]
