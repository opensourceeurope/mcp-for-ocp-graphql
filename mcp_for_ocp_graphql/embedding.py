"""Embedding helpers for the nomic-ai/nomic-embed-text-v1.5 model."""
import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

# Must match the model OpenCrane used at build time (same env var name).
MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5")


@lru_cache(maxsize=1)
def _model():
    return SentenceTransformer(MODEL_NAME, trust_remote_code=True)


def query_text(text: str) -> str:
    """nomic requires a task prefix; queries use the search_query prefix."""
    return f"search_query: {text}"


def embed_query(text: str, model=None) -> list[float]:
    m = model if model is not None else _model()
    vector = m.encode(query_text(text))
    return [float(x) for x in vector]
