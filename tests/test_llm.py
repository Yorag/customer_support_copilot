from __future__ import annotations

from src.llm import _extract_embedding_vector


def test_extract_embedding_vector_supports_top_level_embedding():
    vector = _extract_embedding_vector({"embedding": [0.1, 0.2, 0.3]})

    assert vector == [0.1, 0.2, 0.3]


def test_extract_embedding_vector_supports_openai_style_data_list():
    vector = _extract_embedding_vector(
        {"data": [{"embedding": [0.4, 0.5, 0.6], "index": 0}]}
    )

    assert vector == [0.4, 0.5, 0.6]
