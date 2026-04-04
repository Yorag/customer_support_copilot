from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt_template(name: str) -> str:
    prompt_path = PROMPTS_DIR / name
    return prompt_path.read_text(encoding="utf-8").strip()
