"""Lexical (BM25) search over the baked OpenCrane doc chunks.

The corpus is tiny (~70 chunks of GraphQL guides + a curated query-field map),
so a dense-vector index (PyTorch + an embedding model + Milvus) was pure
overhead — it forced a multi-GB container and a cold-start model load for less
text than a single source file. BM25 over the same chunks is a few hundred
lines of pure Python, needs no model, and for exact GraphQL identifiers
(``expenses``, ``payoutMethod``) lexical matching is as good or better.

``DocSearch`` keeps the same shape as the old vector backend — construct with a
path to the baked ``docs.json`` and call ``search(query, top_k)`` — so the
server/tool layer is unchanged.
"""
import json
import math
import re

# Split on non-alphanumerics AND on camelCase boundaries, so a query like
# "payout method" matches the GraphQL field "payoutMethod" and vice versa.
_WORD = re.compile(r"[A-Za-z0-9]+")
_CAMEL = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, with camelCase words additionally split into parts.

    ``payoutMethod`` -> ``["payoutmethod", "payout", "method"]`` so both the
    whole identifier and its parts are matchable.
    """
    tokens: list[str] = []
    for word in _WORD.findall(text or ""):
        lower = word.lower()
        tokens.append(lower)
        parts = _CAMEL.findall(word)
        if len(parts) > 1:
            tokens.extend(p.lower() for p in parts)
    return tokens


class BM25:
    """Minimal BM25 Okapi ranker over an in-memory list of tokenized documents."""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_tokens = corpus_tokens
        self.doc_len = [len(d) for d in corpus_tokens]
        self.n_docs = len(corpus_tokens)
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0
        # term frequency per document + document frequency per term
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for tokens in corpus_tokens:
            freqs: dict[str, int] = {}
            for t in tokens:
                freqs[t] = freqs.get(t, 0) + 1
            self.tf.append(freqs)
            for term in freqs:
                df[term] = df.get(term, 0) + 1
        # smoothed idf (BM25 Okapi); floored at 0 so common terms never go negative
        self.idf = {
            term: max(0.0, math.log((self.n_docs - freq + 0.5) / (freq + 0.5) + 1.0))
            for term, freq in df.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = [0.0] * self.n_docs
        for i in range(self.n_docs):
            freqs = self.tf[i]
            dl = self.doc_len[i]
            denom_norm = self.k1 * (1 - self.b + self.b * (dl / self.avgdl if self.avgdl else 0.0))
            score = 0.0
            for term in query_tokens:
                f = freqs.get(term)
                if not f:
                    continue
                score += self.idf.get(term, 0.0) * (f * (self.k1 + 1)) / (f + denom_norm)
            out[i] = score
        return out


class DocSearch:
    def __init__(self, docs_path, tokenizer=tokenize):
        with open(docs_path) as f:
            self._docs = json.load(f)
        self._tokenize = tokenizer
        self._bm25 = BM25([tokenizer(d.get("content") or "") for d in self._docs])

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        scores = self._bm25.scores(self._tokenize(query))
        ranked = sorted(range(len(self._docs)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in ranked[:top_k]:
            if scores[i] <= 0:
                break  # no lexical overlap — don't pad with irrelevant chunks
            d = self._docs[i]
            out.append({
                "text": d.get("content"),
                "source": d.get("source_name") or d.get("source_file"),
                "source_url": d.get("source_url") or None,
                "score": round(scores[i], 4),
            })
        return out
