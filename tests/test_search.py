"""Tests for mcp_for_ocp_graphql.search — TDD, written before implementation."""
import shutil
import tempfile

import pytest
from pymilvus import DataType, MilvusClient

from mcp_for_ocp_graphql.search import DEFAULT_COLLECTION, DocSearch


@pytest.fixture
def milvus_db(tmp_path):
    """
    Build a real Milvus Lite collection mirroring the OpenCrane schema (dim 8).
    Yields the db path string; tears down afterwards.
    """
    # pymilvus 3.0.0 requires the path to end with ".db"
    db_path = str(tmp_path / "test_db.db")

    client = MilvusClient(db_path)

    # Explicit schema matching OpenCrane: chunk_id (pk), embedding (vector),
    # content (VARCHAR), source_name (VARCHAR).
    schema = MilvusClient.create_schema()
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=8)
    schema.add_field("content", DataType.VARCHAR, max_length=512)
    schema.add_field("source_name", DataType.VARCHAR, max_length=256)

    # pymilvus 3.0.0 requires an explicit index_type; HNSW works with COSINE
    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE")

    client.create_collection(
        collection_name="test_col",
        schema=schema,
        index_params=index_params,
    )

    client.insert(
        collection_name="test_col",
        data=[
            {
                "chunk_id": "a",
                "embedding": [1, 0, 0, 0, 0, 0, 0, 0],
                "content": "how to list expenses",
                "source_name": "expenses.md",
            },
            {
                "chunk_id": "b",
                "embedding": [0, 1, 0, 0, 0, 0, 0, 0],
                "content": "about backers",
                "source_name": "backers.md",
            },
        ],
    )

    client.close()

    yield db_path

    shutil.rmtree(db_path, ignore_errors=True)


def test_search_ranks_most_similar_first(milvus_db):
    """Querying with [1,0,...] should return the 'expenses' row first."""
    ds = DocSearch(
        milvus_db,
        collection="test_col",
        embedder=lambda q: [1, 0, 0, 0, 0, 0, 0, 0],
    )
    hits = ds.search("anything", top_k=1)
    assert len(hits) == 1
    assert hits[0]["text"] == "how to list expenses"
    assert hits[0]["source"] == "expenses.md"
    assert "score" in hits[0]


def test_search_respects_top_k(milvus_db):
    """top_k=2 should return both rows."""
    ds = DocSearch(
        milvus_db,
        collection="test_col",
        embedder=lambda q: [1, 1, 0, 0, 0, 0, 0, 0],
    )
    hits = ds.search("x", top_k=2)
    assert len(hits) == 2
