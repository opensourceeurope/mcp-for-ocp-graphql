"""Tests for docs_bake.build_docs and the round-trip through DocSearch."""
import json

import pytest

from mcp_for_ocp_graphql.docs_bake import build_docs
from mcp_for_ocp_graphql.search import DocSearch

# chunks.json shape as produced by `opencrane chunk`.
CHUNKS = [
    {
        "chunk_id": "aaa111",
        "chunk_type": "text",
        "content": "How to list expenses in Open Collective",
        "metadata": {"is_complete": True, "source_url": "https://example.com/expenses.md"},
        "source_file": ".opencrane/llmstxt/llms-full.txt",
        "source_name": "oc-06-expenses",
        "token_count": 8,
    },
    {
        "chunk_id": "bbb222",
        "chunk_type": "code_snippet",
        "content": "query { expenses { nodes { id description } } }",
        "metadata": {"is_complete": True, "language": "graphql"},  # no source_url
        "source_file": ".opencrane/llmstxt/llms-full.txt",
        "source_name": "oc-06-expenses",
        "token_count": 10,
    },
]


@pytest.fixture
def chunks_file(tmp_path):
    p = tmp_path / "chunks.json"
    p.write_text(json.dumps(CHUNKS))
    return str(p)


@pytest.fixture
def out_file(tmp_path):
    return str(tmp_path / "docs.json")


def test_build_docs_returns_count(chunks_file, out_file):
    assert build_docs(chunks_file, out_file) == 2


def test_build_docs_projects_expected_fields(chunks_file, out_file):
    build_docs(chunks_file, out_file)
    docs = json.loads(open(out_file).read())
    assert set(docs[0]) == {"chunk_id", "content", "source_name", "source_file", "source_url"}
    assert docs[0]["source_url"] == "https://example.com/expenses.md"
    # a chunk with no metadata.source_url gets an empty string, never a KeyError
    assert docs[1]["source_url"] == ""


def test_baked_docs_are_searchable(chunks_file, out_file):
    build_docs(chunks_file, out_file)
    hits = DocSearch(out_file).search("list expenses", top_k=2)
    assert hits
    assert "expense" in hits[0]["text"].lower()
    assert hits[0]["source"] == "oc-06-expenses"
