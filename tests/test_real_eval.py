from __future__ import annotations

from pathlib import Path

from scripts.run_real_eval import build_report
from scripts import run_real_eval


def test_build_report_distinguishes_judge_failure_from_baseline() -> None:
    report = build_report(
        [
            {
                "sample_id": "sample-1",
                "primary_route": "knowledge_request",
                "expected_primary_route": "knowledge_request",
                "needs_escalation": False,
                "expected_escalation": False,
                "response_quality": None,
                "response_quality_status": "failed",
                "response_quality_baseline": {
                    "overall_score": 4.0,
                    "subscores": {
                        "relevance": 4,
                        "correctness": 4,
                        "intent_alignment": 4,
                        "clarity": 4,
                    },
                    "reason": "baseline only",
                },
                "trajectory_evaluation": {"score": 5.0},
                "http_status": 202,
            },
            {
                "sample_id": "sample-2",
                "primary_route": "technical_issue",
                "expected_primary_route": "technical_issue",
                "needs_escalation": False,
                "expected_escalation": False,
                "response_quality": {
                    "overall_score": 4.25,
                    "subscores": {
                        "relevance": 5,
                        "correctness": 4,
                        "intent_alignment": 4,
                        "clarity": 4,
                    },
                    "reason": "judge ok",
                },
                "response_quality_status": "succeeded",
                "response_quality_baseline": {
                    "overall_score": 4.0,
                    "subscores": {
                        "relevance": 4,
                        "correctness": 4,
                        "intent_alignment": 4,
                        "clarity": 4,
                    },
                    "reason": "baseline only",
                },
                "trajectory_evaluation": {"score": 4.5},
                "http_status": 202,
            },
        ]
    )

    assert report["avg_response_quality_score"] == 4.25
    assert report["avg_trajectory_score"] == 4.75
    assert report["response_quality_judge"] == {
        "succeeded_count": 1,
        "failed_count": 1,
        "unavailable_count": 0,
    }
    assert report["failed_samples"][0]["sample_id"] == "sample-1"
    assert report["failed_samples"][0]["response_quality_status"] == "failed"


def test_run_real_eval_drives_local_worker_before_fetching_trace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_real_eval, "_apply_runtime_overrides", lambda **_: None)
    monkeypatch.setattr(run_real_eval, "_clear_runtime_caches", lambda: None)
    monkeypatch.setattr(run_real_eval, "rebuild_knowledge_index", lambda: None)
    monkeypatch.setattr(
        run_real_eval,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "knowledge": type(
                    "Knowledge",
                    (),
                    {
                        "chroma_persist_directory": tmp_path / "db",
                        "source_document_path": tmp_path / "agency.txt",
                    },
                )(),
                "llm": type("Llm", (), {"chat_model": "test-model"})(),
                "embedding": type("Embedding", (), {"model": "test-embedding"})(),
            },
        )(),
    )

    writes: list[dict] = []

    def fake_write_report(**kwargs):
        payload = {"records": list(kwargs["records"])}
        writes.append(payload)
        return payload

    monkeypatch.setattr(run_real_eval, "_write_report", fake_write_report)

    class FakeWorkerRunner:
        def __init__(self) -> None:
            self.calls = 0

        def run_once(self):
            self.calls += 1
            return None

    worker_runner = FakeWorkerRunner()
    monkeypatch.setattr(run_real_eval, "LocalWorkerRunner", lambda: worker_runner)

    class FakeLocalApiServer:
        def __init__(self, *, host: str, port: int) -> None:
            self.base_url = f"http://{host}:{port}"

        def __enter__(self) -> str:
            return self.base_url

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(run_real_eval, "LocalApiServer", FakeLocalApiServer)

    sample_path = tmp_path / "samples.jsonl"
    report_path = tmp_path / "report.json"
    sample_path.write_text(
        "\n".join(
            [
                '{"sample_id":"sample-1","scenario_type":"route","email_subject":"hello","email_body":"body","expected_primary_route":"knowledge_request","expected_escalation":false,"expected_route_template":"knowledge_request -> draft_reply"}'
            ]
        ),
        encoding="utf-8",
    )

    snapshot_calls = 0

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    class FakeSession:
        def post(self, url: str, json: dict, headers=None, timeout: int = 0):
            if url.endswith("/tickets/ingest-email"):
                return FakeResponse(200, {"ticket_id": "ticket-1", "version": 1})
            if url.endswith("/tickets/ticket-1/run"):
                return FakeResponse(202, {"run_id": "run-1", "trace_id": "trace-1"})
            raise AssertionError(url)

        def get(self, url: str, params=None, timeout: int = 0):
            nonlocal snapshot_calls
            if url.endswith("/tickets/ticket-1"):
                snapshot_calls += 1
                run_status = "running" if snapshot_calls == 1 else "succeeded"
                return FakeResponse(
                    200,
                    {
                        "ticket": {"primary_route": "knowledge_request"},
                        "latest_run": {
                            "run_id": "run-1",
                            "status": run_status,
                            "final_action": "create_draft",
                        },
                    },
                )
            if url.endswith("/tickets/ticket-1/trace"):
                assert params == {"run_id": "run-1"}
                return FakeResponse(
                    200,
                    {
                        "trace_id": "trace-1",
                        "events": [
                            {
                                "event_name": "escalation_decision",
                                "metadata": {"needs_escalation": False},
                                "status": "succeeded",
                            },
                            {
                                "event_name": "draft_reply",
                                "outputs": {"knowledge_summary": "summary"},
                                "status": "succeeded",
                            },
                            {
                                "event_name": "create_gmail_draft",
                                "outputs": {
                                    "draft_versions": [
                                        {
                                            "version_index": 1,
                                            "draft_type": "reply",
                                            "content_text": "Draft body",
                                        }
                                    ]
                                },
                                "status": "succeeded",
                            },
                            {
                                "event_name": "response_quality_judge",
                                "metadata": {"judge_status": "succeeded"},
                                "status": "succeeded",
                            },
                        ],
                        "response_quality": {"overall_score": 4.5},
                        "trajectory_evaluation": {"score": 5.0},
                        "latency_metrics": {},
                        "resource_metrics": {},
                    },
                )
            raise AssertionError(url)

    monkeypatch.setattr(run_real_eval.requests, "Session", FakeSession)

    payload = run_real_eval.run_real_eval(
        samples_path=sample_path,
        report_path=report_path,
        api_base_url=None,
        host="127.0.0.1",
        port=8000,
        request_timeout_seconds=1,
        disable_gmail=True,
        knowledge_source_path=None,
        knowledge_db_path=None,
        rebuild_index=False,
    )

    assert worker_runner.calls >= 1
    assert payload["records"][0]["trace_id"] == "trace-1"
    assert payload["records"][0]["primary_route"] == "knowledge_request"
