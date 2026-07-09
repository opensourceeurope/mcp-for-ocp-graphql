"""Milvus Lite document search for the OpenCrane RAG feature."""
from pymilvus import MilvusClient

from .embedding import embed_query

DEFAULT_COLLECTION = "ai_docs_chunks_v1"


class DocSearch:
    def __init__(self, db_path, collection=DEFAULT_COLLECTION, embedder=embed_query):
        self._client = MilvusClient(db_path)
        self._collection = collection
        self._embedder = embedder
        # pymilvus 3.0 / Milvus Lite: collection must be loaded before search
        if self._client.has_collection(collection):
            self._client.load_collection(collection)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        vector = self._embedder(query)
        results = self._client.search(
            collection_name=self._collection,
            data=[vector],
            limit=top_k,
            output_fields=["content", "source_name", "source_file", "source_url"],
            anns_field="embedding",
        )
        hits = results[0] if results else []
        out = []
        for h in hits:
            entity = h.get("entity", {})
            out.append({
                "text": entity.get("content"),
                "source": entity.get("source_name") or entity.get("source_file"),
                "source_url": entity.get("source_url") or None,
                "score": h.get("distance"),
            })
        return out
