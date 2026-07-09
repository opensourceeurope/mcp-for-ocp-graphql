"""Build a Milvus Lite vector index from OpenCrane chunks + embeddings JSON files.

OpenCrane JSON structures (as produced by ``opencrane chunk`` and ``opencrane embed``):

chunks.json — top-level list, each element:
  {
    "chunk_id":    str   (SHA-256 hex, used as primary key),
    "chunk_type":  str,
    "content":     str,
    "line_start":  int | null,
    "metadata":    dict,
    "source_file": str,
    "source_name": str | null,
    "token_count": int
  }

embeddings.json — top-level dict:
  {
    "model":        str,
    "dimensions":   int,          # e.g. 768 for nomic-embed-text-v1.5
    "created_at":   str (ISO),
    "chunks_sha256":str,
    "embeddings":   [             # list, one per chunk
      {
        "chunk_index": int,
        "chunk_id":    str,       # matches chunk_id in chunks.json
        "vector":      [float]    # dim = embeddings.dimensions
      },
      ...
    ]
  }

The Milvus Lite collection ``ai_docs_chunks_v1`` (default) uses:
  chunk_id    VARCHAR(512)   primary key
  embedding   FLOAT_VECTOR   dim inferred from data
  content     VARCHAR(65535)
  source_name VARCHAR(512)
  source_file VARCHAR(512)
  source_url  VARCHAR(1024)  from chunk ``metadata.source_url`` (may be empty)
with a COSINE / HNSW index on ``embedding``.
"""
from __future__ import annotations

import json
import shutil

from pymilvus import DataType, MilvusClient

DEFAULT_COLLECTION = "ai_docs_chunks_v1"


def build_index(
    chunks_file: str,
    embeddings_file: str,
    db_path: str,
    collection: str = DEFAULT_COLLECTION,
) -> int:
    """Build (or rebuild) a Milvus Lite collection from OpenCrane JSON artefacts.

    Parameters
    ----------
    chunks_file:
        Path to ``.opencrane/chunks.json`` produced by ``opencrane chunk``.
    embeddings_file:
        Path to ``.opencrane/embeddings.json`` produced by ``opencrane embed``.
    db_path:
        Filesystem path for the Milvus Lite database directory (must end in ``.db``).
        Created if absent; dropped-and-recreated if the collection already exists.
    collection:
        Milvus collection name (default ``ai_docs_chunks_v1``).

    Returns
    -------
    int
        Number of rows inserted.
    """
    # ── Load source data ───────────────────────────────────────────────────────
    with open(chunks_file) as f:
        chunks: list[dict] = json.load(f)

    with open(embeddings_file) as f:
        emb_doc: dict = json.load(f)

    dim: int = emb_doc["dimensions"]
    emb_list: list[dict] = emb_doc["embeddings"]

    # Build a chunk_id → vector lookup
    id_to_vector: dict[str, list[float]] = {
        e["chunk_id"]: e["vector"] for e in emb_list
    }

    # Build chunk_id → chunk metadata lookup
    id_to_chunk: dict[str, dict] = {c["chunk_id"]: c for c in chunks}

    # ── Connect to Milvus Lite ─────────────────────────────────────────────────
    client = MilvusClient(db_path)

    # Drop collection if it already exists (idempotent rebuild)
    if client.has_collection(collection):
        client.drop_collection(collection)

    # ── Define schema ──────────────────────────────────────────────────────────
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=512, is_primary=True)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("content", DataType.VARCHAR, max_length=65535)
    schema.add_field("source_name", DataType.VARCHAR, max_length=512)
    schema.add_field("source_file", DataType.VARCHAR, max_length=512)
    schema.add_field("source_url", DataType.VARCHAR, max_length=1024)

    # ── Define index params ────────────────────────────────────────────────────
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        metric_type="COSINE",
        index_type="HNSW",
        params={"M": 16, "efConstruction": 200},
    )

    # ── Create collection ──────────────────────────────────────────────────────
    client.create_collection(
        collection_name=collection,
        schema=schema,
        index_params=index_params,
    )

    # ── Assemble rows ──────────────────────────────────────────────────────────
    rows: list[dict] = []
    for chunk_id, vector in id_to_vector.items():
        chunk = id_to_chunk.get(chunk_id)
        if chunk is None:
            continue  # orphan embedding — skip
        rows.append(
            {
                "chunk_id": chunk_id,
                "embedding": vector,
                "content": (chunk.get("content") or "")[:65535],
                "source_name": (chunk.get("source_name") or "")[:512],
                "source_file": (chunk.get("source_file") or "")[:512],
                "source_url": (((chunk.get("metadata") or {}).get("source_url")) or "")[:1024],
            }
        )

    # ── Insert ────────────────────────────────────────────────────────────────
    if rows:
        client.insert(collection_name=collection, data=rows)

    return len(rows)


def main(argv: list[str] | None = None) -> None:
    """CLI: python -m mcp_for_ocp_graphql.indexer [CHUNKS] [EMBEDDINGS] [DB_PATH]

    Loads OpenCrane chunks + embeddings into the Milvus Lite collection the server
    reads. Used as the pipeline's index step because `opencrane index` targets
    pymilvus <2.6 (single-file DB) while this project runs pymilvus 3.x
    (directory DB) — the on-disk formats are incompatible.
    """
    import sys

    argv = sys.argv[1:] if argv is None else argv
    chunks = argv[0] if len(argv) > 0 else ".opencrane/chunks.json"
    embeddings = argv[1] if len(argv) > 1 else ".opencrane/embeddings.json"
    db_path = argv[2] if len(argv) > 2 else "mcp_for_ocp_graphql/data/milvus.db"
    n = build_index(chunks, embeddings, db_path)
    sys.stderr.write(f"Indexed {n} rows into {db_path} (collection {DEFAULT_COLLECTION})\n")


if __name__ == "__main__":
    main()
