"""Tests for mcp_for_ocp_graphql.embedding — TDD, written before implementation."""
from mcp_for_ocp_graphql.embedding import embed_query, query_text


def test_query_text_prefix():
    assert query_text("how to X") == "search_query: how to X"


def test_embed_query_applies_prefix_and_uses_injected_model():
    """Inject a fake model so no real model load is needed."""
    captured = {}

    class FakeModel:
        def encode(self, s):
            captured["input"] = s
            return [0.1, 0.2, 0.3]

    result = embed_query("hi", model=FakeModel())
    assert result == [0.1, 0.2, 0.3]
    assert captured["input"] == "search_query: hi"


def test_embed_query_real_model_dimension():
    """Slow test — uses the real nomic model downloaded during the spike."""
    result = embed_query("hello world")
    assert len(result) == 768
