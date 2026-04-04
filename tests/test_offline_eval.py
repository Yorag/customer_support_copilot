from __future__ import annotations

import json
from pathlib import Path

from scripts.run_offline_eval import build_report, main


def test_offline_eval_report_records_execution_mode(tmp_path: Path):
    report_path = tmp_path / "eval_report.json"

    payload = main(report_path=report_path, use_real_llm=False)

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["mode"] == {
        "use_real_llm": False,
        "gmail": "fake",
        "knowledge_provider": "fake",
        "policy_provider": "fake",
        "database": "temporary_sqlite",
    }
    assert payload["mode"] == persisted["mode"]
    assert persisted["summary"]["total_samples"] >= 24
    assert len(persisted["records"]) == persisted["summary"]["total_samples"]


def test_build_report_tolerates_missing_response_quality() -> None:
    report = build_report(
        [
            {
                "sample_id": "sample-1",
                "scenario_type": "knowledge_request",
                "primary_route": "knowledge_request",
                "expected_primary_route": "knowledge_request",
                "needs_escalation": False,
                "expected_escalation": False,
                "response_quality": None,
                "response_quality_status": "failed",
                "trajectory_evaluation": {"score": 4.0},
            },
            {
                "sample_id": "sample-2",
                "scenario_type": "commercial_policy_request",
                "primary_route": "commercial_policy_request",
                "expected_primary_route": "commercial_policy_request",
                "needs_escalation": True,
                "expected_escalation": True,
                "response_quality": {"overall_score": 3.5},
                "response_quality_status": "succeeded",
                "trajectory_evaluation": {"score": 5.0},
            },
        ]
    )

    assert report["total_samples"] == 2
    assert report["avg_response_quality_score"] == 3.5
    assert report["avg_trajectory_score"] == 4.5
    assert report["response_quality_judge"] == {
        "succeeded_count": 1,
        "failed_count": 1,
        "unavailable_count": 0,
    }
    assert report["failed_samples"][0]["response_quality_status"] == "failed"
