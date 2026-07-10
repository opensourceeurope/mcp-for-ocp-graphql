"""Tests for the pure-Python BM25 doc search backend."""
import json

import pytest

from mcp_for_ocp_graphql.search import BM25, DocSearch, tokenize


# ── tokenizer ────────────────────────────────────────────────────────────────
def test_tokenize_lowercases_and_splits_on_nonalphanumeric():
    assert tokenize("List, expenses! (v2)") == ["list", "expenses", "v2"]


def test_tokenize_splits_camelcase_keeping_whole_and_parts():
    # payoutMethod -> the whole identifier AND its parts, so "payout method" matches it
    assert tokenize("payoutMethod") == ["payoutmethod", "payout", "method"]


def test_tokenize_handles_empty_and_none():
    assert tokenize("") == []
    assert tokenize(None) == []


# ── BM25 ranker ────────────────────────────────────────────────────────────────
def test_bm25_scores_matching_doc_above_nonmatching():
    corpus = [tokenize("how to list expenses"), tokenize("about backers and tiers")]
    scores = BM25(corpus).scores(tokenize("expenses"))
    assert scores[0] > 0
    assert scores[1] == 0


# ── DocSearch ────────────────────────────────────────────────────────────────
@pytest.fixture
def docs_file(tmp_path):
    p = tmp_path / "docs.json"
    p.write_text(json.dumps([
        {
            "chunk_id": "a",
            "content": "How to list expenses in Open Collective",
            "source_name": "expenses.md",
            "source_file": ".opencrane/x",
            "source_url": "https://example.com/expenses",
        },
        {
            "chunk_id": "b",
            "content": "About backers and contribution tiers",
            "source_name": "backers.md",
            "source_file": ".opencrane/y",
            "source_url": "https://example.com/backers",
        },
    ]))
    return str(p)


def test_search_ranks_most_relevant_first(docs_file):
    hits = DocSearch(docs_file).search("list expenses", top_k=5)
    assert hits[0]["text"] == "How to list expenses in Open Collective"
    assert hits[0]["source"] == "expenses.md"
    assert hits[0]["source_url"] == "https://example.com/expenses"
    assert "score" in hits[0]


def test_search_respects_top_k(docs_file):
    # a query matching both docs, capped at 1
    hits = DocSearch(docs_file).search("open collective contribution expenses", top_k=1)
    assert len(hits) == 1


def test_search_drops_zero_score_chunks(docs_file):
    # "backers" only overlaps the second doc — the first must not be padded in
    hits = DocSearch(docs_file).search("backers", top_k=5)
    assert len(hits) == 1
    assert hits[0]["source"] == "backers.md"


def test_search_returns_empty_when_no_overlap(docs_file):
    assert DocSearch(docs_file).search("kubernetes helm chart", top_k=5) == []
