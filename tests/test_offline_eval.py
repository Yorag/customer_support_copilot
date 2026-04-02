from __future__ import annotations

import json
from pathlib import Path

from scripts.run_offline_eval import main


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
