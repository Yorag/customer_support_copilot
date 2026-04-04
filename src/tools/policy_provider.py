from __future__ import annotations

from src.contracts.protocols import PolicyProviderProtocol


DEFAULT_POLICY = """
Follow these baseline customer support rules:
- Do not promise refunds, credits, or policy exceptions unless explicitly supported by policy.
- Be concise, polite, and specific about next steps.
- If information is missing, ask a focused clarifying question instead of guessing.
""".strip()


POLICY_BY_CATEGORY = {
    "product_enquiry": """
Provide accurate product information grounded in the knowledge base.
If product details are uncertain, say so explicitly.
""".strip(),
    "knowledge_request": """
Provide accurate product information grounded in the knowledge base.
If product details are uncertain, say so explicitly.
""".strip(),
    "customer_complaint": """
Acknowledge the issue, avoid defensiveness, and avoid making irreversible commitments.
Offer clear next steps or escalation when needed.
""".strip(),
    "technical_issue": """
Acknowledge the failure, stay factual about troubleshooting, and ask for targeted diagnostics when details are incomplete.
Do not claim the issue is fixed unless evidence supports it.
""".strip(),
    "commercial_policy_request": """
Stay within explicit policy boundaries.
Do not promise refunds, credits, compensation, or SLA exceptions without approved policy support.
""".strip(),
    "customer_feedback": """
Thank the customer, acknowledge the suggestion, and avoid implying roadmap commitments.
""".strip(),
    "feedback_intake": """
Thank the customer, acknowledge the suggestion or complaint, and avoid implying roadmap commitments.
""".strip(),
    "unrelated": """
Do not invent support scope. Politely explain the limitation or redirect if appropriate.
""".strip(),
}


class StaticPolicyProvider(PolicyProviderProtocol):
    def get_policy(self, category: str | None = None) -> str:
        if category is None:
            return DEFAULT_POLICY

        category_policy = POLICY_BY_CATEGORY.get(category)
        if not category_policy:
            return DEFAULT_POLICY

        return f"{DEFAULT_POLICY}\n\nCategory-specific guidance:\n{category_policy}"
