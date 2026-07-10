"""Bake the OpenCrane chunks into the slim ``docs.json`` the server searches.

``opencrane chunk`` writes ``.opencrane/chunks.json`` (a rich list with per-chunk
metadata). The lexical search backend (:mod:`mcp_for_ocp_graphql.search`) only
needs the text plus a few provenance fields, so this step projects each chunk
down to that and writes the result into the package data dir, where it ships in
the wheel and is loaded at query time. No embeddings, no vector DB — the whole
artefact is a few tens of KB of JSON.

chunks.json — top-level list, each element:
  {
    "chunk_id":    str,
    "content":     str,
    "metadata":    { "source_url": str, "section_anchor": str | null, ... },
    "source_file": str,
    "source_name": str | null,
    ...
  }

docs.json — top-level list, each element:
  { "chunk_id", "content", "source_name", "source_file", "source_url" }

``source_url`` is a GitHub blob URL. When the chunk carries a ``section_anchor``
(OpenCrane emits a GitHub-compatible heading slug, e.g. ``with-a-personal-token``),
it is appended as a ``#fragment`` so the citation deep-links to the exact section
rather than the top of the page. Chunks without an anchor keep the page URL.
"""
from __future__ import annotations

import json


def _source_url(meta: dict) -> str:
    """GitHub blob URL for the chunk, deep-linked to its section when known."""
    url = meta.get("source_url") or ""
    anchor = meta.get("section_anchor")
    if url and anchor:
        return f"{url}#{anchor}"
    return url


def build_docs(chunks_file: str, out_file: str) -> int:
    """Project ``chunks_file`` into the slim ``out_file`` search corpus.

    Returns the number of chunks written.
    """
    with open(chunks_file) as f:
        chunks: list[dict] = json.load(f)

    docs = [
        {
            "chunk_id": c.get("chunk_id"),
            "content": c.get("content") or "",
            "source_name": c.get("source_name") or "",
            "source_file": c.get("source_file") or "",
            "source_url": _source_url(c.get("metadata") or {}),
        }
        for c in chunks
    ]

    with open(out_file, "w") as f:
        json.dump(docs, f, indent=2)

    return len(docs)


def main(argv: list[str] | None = None) -> None:
    """CLI: python -m mcp_for_ocp_graphql.docs_bake [CHUNKS] [OUT]"""
    import sys

    argv = sys.argv[1:] if argv is None else argv
    chunks = argv[0] if len(argv) > 0 else ".opencrane/chunks.json"
    out = argv[1] if len(argv) > 1 else "mcp_for_ocp_graphql/data/docs.json"
    n = build_docs(chunks, out)
    sys.stderr.write(f"Baked {n} chunks into {out}\n")


if __name__ == "__main__":
    main()
