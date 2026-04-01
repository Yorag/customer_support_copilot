from __future__ import annotations

from src.tools.types import PolicyProviderProtocol


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
    "customer_complaint": """
Acknowledge the issue, avoid defensiveness, and avoid making irreversible commitments.
Offer clear next steps or escalation when needed.
""".strip(),
    "customer_feedback": """
Thank the customer, acknowledge the suggestion, and avoid implying roadmap commitments.
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
