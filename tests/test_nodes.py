from __future__ import annotations

from types import SimpleNamespace

from src.nodes import Nodes
from src.state import Email
from src.tools.types import KnowledgeAnswer


class FakeGmailClient:
    def __init__(self, emails: list[dict] | None = None) -> None:
        self._emails = emails or []
        self.created_drafts: list[tuple[Email, str]] = []

    def fetch_unanswered_emails(self, max_results=None):
        return list(self._emails)

    def create_draft_reply(self, initial_email, reply_text):
        self.created_drafts.append((initial_email, reply_text))
        return {"id": "draft_001"}

    def send_reply(self, initial_email, reply_text):
        return {"id": "sent_001"}


class FakeKnowledgeProvider:
    def answer_questions(self, questions):
        return [
            KnowledgeAnswer(question=question, answer=f"answer for {question}")
            for question in questions
        ]


class FakePolicyProvider:
    def get_policy(self, category=None):
        return f"policy for {category or 'default'}"


class FakeTicketStore:
    def ping(self):
        return True

    def session_scope(self):
        raise AssertionError("session_scope should not be used in this test")


class FakeAgents:
    def __init__(self) -> None:
        self.categorize_email = SimpleNamespace(
            invoke=lambda _: SimpleNamespace(category=SimpleNamespace(value="product_enquiry"))
        )
        self.design_rag_queries = SimpleNamespace(
            invoke=lambda _: SimpleNamespace(queries=["pricing", "annual billing"])
        )
        self.email_writer = SimpleNamespace(
            invoke=lambda payload: SimpleNamespace(
                email=f"draft based on {payload['email_information']}"
            )
        )
        self.email_proofreader = SimpleNamespace(
            invoke=lambda _: SimpleNamespace(send=True, feedback="looks good")
        )


class FakeServices:
    def __init__(self, gmail_client):
        self.gmail_client = gmail_client
        self.knowledge_provider = FakeKnowledgeProvider()
        self.policy_provider = FakePolicyProvider()
        self.ticket_store = FakeTicketStore()


def test_load_new_emails_uses_gmail_provider(sample_email_payload):
    gmail_client = FakeGmailClient(emails=[sample_email_payload])
    nodes = Nodes(agents=FakeAgents(), service_container=FakeServices(gmail_client))

    result = nodes.load_new_emails({})

    assert len(result["emails"]) == 1
    assert result["emails"][0].subject == "Pricing question"


def test_retrieve_from_rag_uses_knowledge_provider():
    nodes = Nodes(
        agents=FakeAgents(),
        service_container=FakeServices(FakeGmailClient()),
    )

    result = nodes.retrieve_from_rag({"rag_queries": ["pricing", "billing"]})

    assert "pricing" in result["retrieved_documents"]
    assert "answer for billing" in result["retrieved_documents"]


def test_create_draft_response_uses_gmail_provider(sample_email_payload):
    gmail_client = FakeGmailClient()
    nodes = Nodes(agents=FakeAgents(), service_container=FakeServices(gmail_client))
    email = Email(**sample_email_payload)

    result = nodes.create_draft_response(
        {
            "current_email": email,
            "generated_email": "Here is the answer",
        }
    )

    assert result == {"retrieved_documents": "", "trials": 0}
    assert gmail_client.created_drafts == [(email, "Here is the answer")]
