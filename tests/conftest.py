from __future__ import annotations

import json
from pathlib import Path

import pytest


TESTS_ROOT = Path(__file__).resolve().parent
SAMPLES_ROOT = TESTS_ROOT / "samples"


@pytest.fixture
def sample_email_payload() -> dict:
    sample_path = SAMPLES_ROOT / "emails" / "product_enquiry.json"
    return json.loads(sample_path.read_text(encoding="utf-8"))
