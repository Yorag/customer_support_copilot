from __future__ import annotations

import json
import argparse
import sys
from collections import Counter
from pathlib import Path
from tempfile import mkstemp
from os import close

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.app import create_app
from src.api.dependencies import get_container
from src.agents import Agents
from src.config import validate_required_settings
from src.core_schema import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.session import build_engine, create_session_factory
from src.structure_outputs import (
    DraftingOutput,
    KnowledgePolicyOutput,
    QaHandoffOutput,
    TriageOutput,
)
from src.tools.service_container import ServiceContainer
from src.tools.ticket_store import SqlAlchemyTicketStore
from src.triage import TriageDecision, TriageDecisionService


DEFAULT_SAMPLES_PATH = PROJECT_ROOT / "tests" / "samples" / "eval" / "customer_support_eval.jsonl"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "tests" / "samples" / "eval" / "customer_support_eval_report.json"


class FakeEvalGmailClient:
    def create_draft_reply(self, initial_email, reply_text):
        return {"id": f"gmail-draft-{generate_prefixed_id(EntityIdPrefix.DRAFT)}"}


class FakeEvalKnowledgeProvider:
    def answer_questions(self, questions):
        return [
            type("Answer", (), {"question": question, "answer": f"answer for {question}"})()
            for question in questions
        ]


class FakeEvalPolicyProvider:
    def get_policy(self, category=None):
        return f"policy for {category or 'default'}"


class HybridEvalAgents(Agents):
    """Uses a real chat model for structured generation while keeping local fallbacks available."""

    def __init__(self, *, triage_service: TriageDecisionService | None = None):
        super().__init__(triage_service=triage_service)

    def triage_email_with_rules(
        self,
        *,
        subject: str | None,
        email: str,
        context=None,
    ):
        structured = self.triage_email.invoke({"subject": subject or "", "email": email})
        rule_based = self.triage_service.evaluate(subject=subject, body=email, context=context)
        merged = TriageOutput.model_validate(
            {
                **structured.model_dump(mode="json"),
                "routing_reason": (
                    structured.routing_reason.strip()
                    if structured.routing_reason.strip()
                    else rule_based.output.routing_reason
                ),
            }
        )
        return TriageDecision(
            output=merged,
            selected_rule="real_llm_structured_output",
            matched_rules=("real_llm_structured_output",),
            priority_reasons=rule_based.priority_reasons,
            escalation_reasons=rule_based.escalation_reasons,
            clarification_reasons=rule_based.clarification_reasons,
        )

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
        prompt = (
            "Return JSON for KnowledgePolicyOutput.\n"
            f"primary_route={primary_route}\n"
            f"response_strategy={response_strategy}\n"
            f"normalized_email={normalized_email}\n"
            f"knowledge_answers={json.dumps(knowledge_answers or [], ensure_ascii=True)}\n"
            f"policy_notes={policy_notes}\n"
            f"knowledge_confidence={knowledge_confidence}\n"
            f"needs_escalation={needs_escalation}\n"
            "Keep outputs factual and bounded by the provided evidence."
        )
        return self._llm.with_structured_output(KnowledgePolicyOutput).invoke(prompt)

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
        prompt = (
            "Return JSON for DraftingOutput.\n"
            f"customer_email={customer_email}\n"
            f"subject={subject}\n"
            f"primary_route={primary_route}\n"
            f"response_strategy={response_strategy}\n"
            f"normalized_email={normalized_email}\n"
            f"knowledge_summary={knowledge_summary}\n"
            f"policy_notes={policy_notes}\n"
            f"rewrite_guidance={json.dumps(rewrite_guidance or [], ensure_ascii=True)}\n"
            "Write a concise support reply aligned with the route and policy boundaries."
        )
        return self._llm.with_structured_output(DraftingOutput).invoke(prompt)

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
        prompt = (
            "Return JSON for QaHandoffOutput.\n"
            f"primary_route={primary_route}\n"
            f"draft_text={draft_text}\n"
            f"knowledge_confidence={knowledge_confidence}\n"
            f"needs_escalation={needs_escalation}\n"
            f"rewrite_count={rewrite_count}\n"
            f"policy_notes={policy_notes}\n"
            "Approve only if the draft is safe, relevant, and within policy."
        )
        return self._llm.with_structured_output(QaHandoffOutput).invoke(prompt)


def _build_app_and_store(*, use_real_llm: bool = False):
    fd, path = mkstemp(suffix=".db")
    close(fd)
    engine = build_engine(f"sqlite+pysqlite:///{path}")
    Base.metadata.create_all(engine)
    store = SqlAlchemyTicketStore(
        engine=engine,
        session_factory=create_session_factory(engine),
    )
    app = create_app()
    app.dependency_overrides[get_container] = lambda: ServiceContainer(
        agents_factory=lambda: HybridEvalAgents() if use_real_llm else Agents(),
        gmail_client_factory=lambda: FakeEvalGmailClient(),
        knowledge_provider_factory=lambda: FakeEvalKnowledgeProvider(),
        policy_provider_factory=lambda: FakeEvalPolicyProvider(),
        ticket_store_factory=lambda: store,
    )
    return app


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_report(records: list[dict]) -> dict:
    route_hits = sum(
        1 for item in records if item["primary_route"] == item["expected_primary_route"]
    )
    escalation_hits = sum(
        1
        for item in records
        if item["needs_escalation"] == item["expected_escalation"]
    )
    quality_scores = [item["response_quality"]["overall_score"] for item in records]
    trajectory_scores = [item["trajectory_evaluation"]["score"] for item in records]
    failures = [
        {
            "sample_id": item["sample_id"],
            "route_mismatch": item["primary_route"] != item["expected_primary_route"],
            "escalation_mismatch": item["needs_escalation"] != item["expected_escalation"],
            "trajectory_score": item["trajectory_evaluation"]["score"],
        }
        for item in records
        if item["primary_route"] != item["expected_primary_route"]
        or item["needs_escalation"] != item["expected_escalation"]
        or item["trajectory_evaluation"]["score"] < 5.0
    ]

    return {
        "total_samples": len(records),
        "scenario_counts": dict(Counter(item["scenario_type"] for item in records)),
        "route_accuracy": round(route_hits / len(records), 3) if records else 0.0,
        "escalation_accuracy": round(escalation_hits / len(records), 3) if records else 0.0,
        "avg_response_quality_score": round(sum(quality_scores) / len(quality_scores), 3)
        if quality_scores
        else 0.0,
        "avg_trajectory_score": round(sum(trajectory_scores) / len(trajectory_scores), 3)
        if trajectory_scores
        else 0.0,
        "failed_samples": failures,
    }


def main(
    samples_path: Path = DEFAULT_SAMPLES_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    *,
    use_real_llm: bool = False,
) -> dict:
    from fastapi.testclient import TestClient

    if use_real_llm:
        validate_required_settings(("LLM_API_KEY",))

    app = _build_app_and_store(use_real_llm=use_real_llm)
    client = TestClient(app)
    records: list[dict] = []

    for index, sample in enumerate(load_jsonl(samples_path), start=1):
        ingest = client.post(
            "/tickets/ingest-email",
            json={
                "source_channel": "gmail",
                "source_thread_id": f"eval-thread-{sample['sample_id']}",
                "source_message_id": f"<{sample['sample_id']}@eval.local>",
                "sender_email_raw": '"Eval User" <eval@example.com>',
                "subject": sample["email_subject"],
                "body_text": sample["email_body"],
                "message_timestamp": f"2026-04-02T10:{index:02d}:00+08:00",
                "attachments": [],
            },
        )
        ingest_payload = ingest.json()
        ticket_id = ingest_payload["ticket_id"]
        run = client.post(
            f"/tickets/{ticket_id}/run",
            json={
                "ticket_version": ingest_payload["version"],
                "trigger_type": "offline_eval",
                "force_retry": False,
            },
            headers={"X-Actor-Id": "offline-eval", "X-Request-Id": sample["sample_id"]},
        )
        if run.status_code not in {202, 502}:
            raise RuntimeError(f"Unexpected eval run status {run.status_code}: {run.text}")

        if run.status_code == 202:
            run_payload = run.json()
            trace = client.get(f"/tickets/{ticket_id}/trace", params={"run_id": run_payload["run_id"]})
            trace_payload = trace.json()
        else:
            run_payload = run.json()["error"]["details"]
            trace = client.get(f"/tickets/{ticket_id}/trace", params={"run_id": run_payload["run_id"]})
            trace_payload = trace.json()

        snapshot = client.get(f"/tickets/{ticket_id}").json()
        records.append(
            {
                "sample_id": sample["sample_id"],
                "scenario_type": sample["scenario_type"],
                "trace_id": trace_payload["trace_id"],
                "primary_route": snapshot["ticket"]["primary_route"],
                "expected_primary_route": sample["expected_primary_route"],
                "needs_escalation": any(
                    event["event_name"] == "escalation_decision"
                    and bool((event.get("metadata") or {}).get("needs_escalation"))
                    for event in trace_payload["events"]
                ),
                "expected_escalation": sample["expected_escalation"],
                "final_action": next(
                    (
                        (event.get("metadata") or {}).get("final_action")
                        for event in trace_payload["events"]
                        if event["event_name"] == "final_action"
                    ),
                    snapshot.get("latest_run", {}) or {},
                ),
                "response_quality": trace_payload["response_quality"],
                "trajectory_evaluation": trace_payload["trajectory_evaluation"],
                "latency_metrics": trace_payload["latency_metrics"],
                "resource_metrics": trace_payload["resource_metrics"],
            }
        )

    report = build_report(records)
    payload = {
        "mode": {
            "use_real_llm": use_real_llm,
            "gmail": "fake",
            "knowledge_provider": "fake",
            "policy_provider": "fake",
            "database": "temporary_sqlite",
        },
        "records": records,
        "summary": report,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run offline evaluation for the ticket workflow.")
    parser.add_argument(
        "--samples-path",
        type=Path,
        default=DEFAULT_SAMPLES_PATH,
        help="Path to the JSONL sample set.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Path to write the evaluation report JSON.",
    )
    parser.add_argument(
        "--use-real-llm",
        action="store_true",
        help="Use the configured chat model for triage/drafting/QA while keeping Gmail, providers, and DB isolated.",
    )
    args = parser.parse_args()
    main(
        samples_path=args.samples_path,
        report_path=args.report_path,
        use_real_llm=args.use_real_llm,
    )
