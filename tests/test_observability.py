from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.observability import validate_judge_output


def test_validate_judge_output_requires_fixed_schema():
    result = validate_judge_output(
        {
            "relevance": 5,
            "correctness": 4,
            "intent_alignment": 4,
            "clarity": 4,
            "reason": "schema ok",
        }
    )
    assert result.overall_score == 4.25

    with pytest.raises(ValueError):
        validate_judge_output(
            {
                "relevance": 5,
                "correctness": 4,
                "intent_alignment": 4,
                "clarity": 4,
            }
        )


def test_eval_samples_cover_minimum_v1_surface():
    sample_path = (
        Path(__file__).resolve().parent / "samples" / "eval" / "customer_support_eval.jsonl"
    )
    rows = [
        json.loads(line)
        for line in sample_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) >= 24
    assert len({row["scenario_type"] for row in rows}) >= 8
