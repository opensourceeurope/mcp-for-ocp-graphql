"""TDD tests for indexer.build_index and round-trip through DocSearch."""
import json
import shutil
import tempfile
import os

import pytest

from mcp_for_ocp_graphql.indexer import build_index
from mcp_for_ocp_graphql.search import DocSearch

# --- Synthetic fixtures matching REAL OpenCrane JSON structure ---
# chunks.json: top-level list, each item has keys:
#   chunk_id, chunk_type, content, line_start, metadata, source_file, source_name, token_count
CHUNKS = [
    {
        "chunk_id": "aaa111",
        "chunk_type": "text",
        "content": "How to list expenses in Open Collective",
        "line_start": None,
        "metadata": {"is_complete": True, "source_url": "https://example.com/expenses.md"},
        "source_file": ".opencrane/llmstxt/llms-full.txt",
        "source_name": "oc-06-expenses",
        "token_count": 8,
    },
    {
        "chunk_id": "bbb222",
        "chunk_type": "code_snippet",
        "content": "query { expenses { nodes { id description } } }",
        "line_start": None,
        "metadata": {"is_complete": True, "language": "graphql"},
        "source_file": ".opencrane/llmstxt/llms-full.txt",
        "source_name": "oc-06-expenses",
        "token_count": 10,
    },
]

# embeddings.json: top-level dict with keys:
#   model, dimensions, created_at, chunks_sha256, embeddings (list)
# Each item in embeddings list has: chunk_index, chunk_id, vector (list of floats)
DIM = 8
EMBEDDINGS = {
    "model": "test-model",
    "dimensions": DIM,
    "created_at": "2026-01-01T00:00:00+00:00",
    "chunks_sha256": "deadbeef",
    "embeddings": [
        {"chunk_index": 0, "chunk_id": "aaa111", "vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]},
        {"chunk_index": 1, "chunk_id": "bbb222", "vector": [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]},
    ],
}


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def chunks_file(tmp_dir):
    p = tmp_dir / "chunks.json"
    p.write_text(json.dumps(CHUNKS))
    return str(p)


@pytest.fixture
def embeddings_file(tmp_dir):
    p = tmp_dir / "embeddings.json"
    p.write_text(json.dumps(EMBEDDINGS))
    return str(p)


@pytest.fixture
def db_path(tmp_dir):
    return str(tmp_dir / "test_index.db")


def test_build_index_returns_chunk_count(chunks_file, embeddings_file, db_path):
    count = build_index(chunks_file, embeddings_file, db_path)
    assert count == 2


def test_build_index_creates_db(chunks_file, embeddings_file, db_path):
    build_index(chunks_file, embeddings_file, db_path)
    # pymilvus 3.0 MilvusClient creates a directory at the .db path
    assert os.path.exists(db_path)


def test_build_index_idempotent_drop_recreate(chunks_file, embeddings_file, db_path):
    """Calling build_index twice should not fail (drop-if-exists)."""
    build_index(chunks_file, embeddings_file, db_path)
    count = build_index(chunks_file, embeddings_file, db_path)
    assert count == 2


def test_search_returns_hit_via_docsearch(chunks_file, embeddings_file, db_path):
    """After indexing, DocSearch with a synthetic embedder should return our chunk."""
    build_index(chunks_file, embeddings_file, db_path)

    # Use a fake embedder that returns a vector close to chunk aaa111
    def fake_embedder(query: str) -> list[float]:
        # Return a vector identical to aaa111 so it should be the top hit
        return [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

    ds = DocSearch(db_path, embedder=fake_embedder)
    results = ds.search("expenses", top_k=2)

    assert len(results) >= 1
    # Top hit should be the expenses chunk (aaa111)
    top = results[0]
    assert "expenses" in top["text"].lower() or "expense" in top["text"].lower()
    assert top["source"] == "oc-06-expenses"
    assert top["source_url"] == "https://example.com/expenses.md"
    assert top["score"] is not None
