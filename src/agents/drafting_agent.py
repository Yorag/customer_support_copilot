from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.prompts import PromptTemplate

from src.contracts.outputs import DraftingOutput
from src.llm.runtime import LlmInvocationResult
from src.prompts.loader import load_prompt_template


@dataclass(frozen=True)
class DraftingAgentResult:
    output: DraftingOutput
    llm_invocation: LlmInvocationResult | None
    fallback_used: bool
    guardrails_adjusted: bool


class DraftingAgentMixin:
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
        allowed_actions: list[str] | None = None,
        disallowed_actions: list[str] | None = None,
    ) -> DraftingOutput:
        return self.drafting_agent_detailed(
            customer_email=customer_email,
            subject=subject,
            primary_route=primary_route,
            response_strategy=response_strategy,
            normalized_email=normalized_email,
            knowledge_summary=knowledge_summary,
            policy_notes=policy_notes,
            rewrite_guidance=rewrite_guidance,
            allowed_actions=allowed_actions,
            disallowed_actions=disallowed_actions,
        ).output

    def drafting_agent_detailed(
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
        allowed_actions: list[str] | None = None,
        disallowed_actions: list[str] | None = None,
    ) -> DraftingAgentResult:
        deterministic_output = self._build_deterministic_drafting_output(
            customer_email=customer_email,
            subject=subject,
            primary_route=primary_route,
            response_strategy=response_strategy,
            normalized_email=normalized_email,
            knowledge_summary=knowledge_summary,
            policy_notes=policy_notes,
            rewrite_guidance=rewrite_guidance,
            allowed_actions=allowed_actions,
            disallowed_actions=disallowed_actions,
        )
        try:
            llm_invocation = self.invoke_drafting_agent(
                customer_email=customer_email,
                subject=subject,
                primary_route=primary_route,
                response_strategy=response_strategy,
                normalized_email=normalized_email,
                knowledge_summary=knowledge_summary,
                policy_notes=policy_notes,
                rewrite_guidance=rewrite_guidance,
                allowed_actions=allowed_actions,
                disallowed_actions=disallowed_actions,
            )
        except Exception:
            return DraftingAgentResult(
                output=deterministic_output,
                llm_invocation=None,
                fallback_used=True,
                guardrails_adjusted=False,
            )

        merged_output = self._merge_drafting_outputs(
            llm_output=llm_invocation.parsed_output,
            deterministic_output=deterministic_output,
        )
        return DraftingAgentResult(
            output=merged_output,
            llm_invocation=llm_invocation,
            fallback_used=False,
            guardrails_adjusted=(
                merged_output.model_dump(mode="json")
                != llm_invocation.parsed_output.model_dump(mode="json")
            ),
        )

    def invoke_drafting_agent(
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
        allowed_actions: list[str] | None = None,
        disallowed_actions: list[str] | None = None,
    ) -> LlmInvocationResult:
        prompt_template = load_prompt_template("drafting_agent.txt")
        return self._runtime.invoke_structured(
            PromptTemplate(
                template=prompt_template,
                input_variables=[
                    "customer_email",
                    "subject",
                    "primary_route",
                    "response_strategy",
                    "normalized_email",
                    "knowledge_summary",
                    "policy_notes",
                    "rewrite_guidance_json",
                    "allowed_actions_json",
                    "disallowed_actions_json",
                ],
            ),
            schema=DraftingOutput,
            inputs={
                "customer_email": customer_email,
                "subject": subject,
                "primary_route": primary_route,
                "response_strategy": response_strategy,
                "normalized_email": normalized_email,
                "knowledge_summary": knowledge_summary,
                "policy_notes": policy_notes,
                "rewrite_guidance_json": json.dumps(
                    rewrite_guidance or [],
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                "allowed_actions_json": json.dumps(
                    allowed_actions or [],
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                "disallowed_actions_json": json.dumps(
                    disallowed_actions or [],
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            },
        )

    def _build_deterministic_drafting_output(
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
        allowed_actions: list[str] | None = None,
        disallowed_actions: list[str] | None = None,
    ) -> DraftingOutput:
        guidance_text = ""
        if rewrite_guidance:
            guidance_text = "\n\nRewrite guidance:\n- " + "\n- ".join(rewrite_guidance)

        greeting = "Hello,"
        closing = "\n\nBest regards"

        if primary_route == "knowledge_request":
            body = (
                "Thanks for your question. Based on the available product "
                "information, here is the most relevant guidance:\n\n"
                f"{knowledge_summary or 'We are reviewing the relevant capability details.'}"
            )
            rationale = (
                "Answer mode uses retrieved product knowledge and avoids unsupported claims."
            )
        elif primary_route == "technical_issue":
            body = (
                "We reviewed the issue details you shared and are treating this "
                "as a technical problem.\n\n"
                f"{knowledge_summary or 'We will continue troubleshooting based on the reported symptoms.'}"
            )
            rationale = (
                "Troubleshooting mode keeps the reply factual and grounded in the "
                "reported diagnostics."
            )
        elif primary_route == "commercial_policy_request":
            body = (
                "We received your billing or policy-related request and will "
                "handle it within the applicable policy boundaries.\n\n"
                f"{policy_notes}"
            )
            rationale = (
                "Policy-constrained drafting sets expectations without making "
                "unsupported commitments."
            )
        elif primary_route == "feedback_intake":
            body = (
                "Thank you for sharing your feedback. We have recorded it for the "
                "team and will use it to inform follow-up work where appropriate."
            )
            rationale = (
                "Acknowledgement mode confirms receipt without implying roadmap commitments."
            )
        else:
            body = (
                "We received your message, but it does not appear to match the "
                "supported customer support scope for this workflow."
            )
            rationale = (
                "Out-of-scope drafting stays concise and avoids inventing unsupported assistance."
            )

        draft_text = f"{greeting}\n\n{body}{guidance_text}{closing}"
        return DraftingOutput(
            draft_text=draft_text,
            draft_rationale=rationale,
            applied_response_strategy=response_strategy,
        )

    def _merge_drafting_outputs(
        self,
        *,
        llm_output: DraftingOutput,
        deterministic_output: DraftingOutput,
    ) -> DraftingOutput:
        draft_text = llm_output.draft_text.strip() or deterministic_output.draft_text
        draft_rationale = (
            llm_output.draft_rationale.strip() or deterministic_output.draft_rationale
        )
        return DraftingOutput(
            draft_text=draft_text,
            draft_rationale=draft_rationale,
            applied_response_strategy=deterministic_output.applied_response_strategy,
        )


def drafting_agent(*args, **kwargs) -> DraftingOutput:
    return DraftingAgentMixin().drafting_agent(*args, **kwargs)


__all__ = ["DraftingAgentMixin", "DraftingAgentResult", "drafting_agent"]
