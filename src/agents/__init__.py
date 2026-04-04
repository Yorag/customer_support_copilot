from __future__ import annotations

from src.llm.runtime import LlmInvocationResult, LlmRuntime
from src.triage import TriageDecisionService

from .drafting_agent import DraftingAgentMixin
from .knowledge_policy_agent import KnowledgePolicyAgentMixin
from .qa_handoff_agent import QaHandoffAgentMixin
from .triage_agent import TriageAgentMixin, TriageMergeResult


class Agents(
    TriageAgentMixin,
    KnowledgePolicyAgentMixin,
    DraftingAgentMixin,
    QaHandoffAgentMixin,
):
    def __init__(self, *, triage_service: TriageDecisionService | None = None):
        self.triage_service = triage_service or TriageDecisionService()
        self._runtime = LlmRuntime(temperature=0.1)


__all__ = ["Agents", "LlmInvocationResult", "LlmRuntime", "TriageMergeResult"]
