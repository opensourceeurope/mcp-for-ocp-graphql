"""Real end-to-end checks — opt-in, run after e.g. bumping OpenCrane:

    uv run pytest -m e2e

Builds the MCP server exactly as ``app_stdio.main`` does (the real baked
``schema.json`` + the OpenCrane-built ``milvus.db``), then drives every tool
through the real ``mcp.call_tool`` dispatch and asserts each returns what's
expected — including a LIVE, tokenless read-only query against the public Open
Collective API. This proves the whole stack works together: tool registration,
schema_lookup over the real schema, search_docs over the OpenCrane index (with
source_url), and the graphql_query proxy against production.

Excluded from the default suite (see pyproject ``addopts``) because it downloads
the embedding model and hits the network.
"""
import asyncio
import json
import socket

import pytest

from mcp_for_ocp_graphql.app_stdio import load_doc_search, load_schema
from mcp_for_ocp_graphql.schema_index import SchemaIndex
from mcp_for_ocp_graphql.server import build_server

pytestmark = pytest.mark.e2e

ENDPOINT = "https://api.opencollective.com/graphql/v2"
EXPECTED_TOOLS = {"graphql_query", "schema_lookup", "search_docs"}


def _tool_text(result) -> str:
    """Extract the text payload from an MCP call_tool result."""
    content_list = result[0]
    item = content_list[0]
    return item.text if hasattr(item, "text") else str(item)


def _online(host="api.opencollective.com", port=443, timeout=5) -> bool:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def server():
    """The real server, built like app_stdio: baked schema + baked milvus.db, anonymous."""
    doc_search = load_doc_search()
    if doc_search is None:
        pytest.skip("baked milvus.db not present — build the index (corpus-refresh) first")
    index = SchemaIndex(load_schema())
    return build_server(index, endpoint=ENDPOINT, token=None, doc_search=doc_search)


def test_mcp_exposes_exactly_the_expected_tools(server):
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == EXPECTED_TOOLS


def test_schema_lookup_returns_real_expenses_query_args(server):
    out = _tool_text(asyncio.run(server.call_tool("schema_lookup", {"name": "expenses"})))
    data = json.loads(out)
    assert data["kind"] == "query"
    argnames = {a["name"] for a in data["args"]}
    # stable, well-known args on the expenses query
    assert {"limit", "offset", "host", "dateFrom"} <= argnames


def test_search_docs_returns_relevant_hit_with_source_url(server):
    out = _tool_text(asyncio.run(server.call_tool("search_docs", {"query": "how do I list expenses", "top_k": 3})))
    hits = json.loads(out)
    assert hits, "search_docs returned no hits"
    assert any("xpense" in (h.get("text") or "") for h in hits), f"no expense-related hit: {hits}"
    assert all(h.get("source_url") for h in hits), f"hits missing source_url: {hits}"


def test_graphql_query_live_public_collective(server):
    """Live, tokenless read-only query against the public OC API over the asyncapi collective."""
    if not _online():
        pytest.skip("api.opencollective.com unreachable — network required")
    query = 'query { account(slug: "asyncapi") { slug name type currency } }'
    out = _tool_text(asyncio.run(server.call_tool("graphql_query", {"query": query})))
    data = json.loads(out)
    account = data["data"]["account"]
    assert account["slug"] == "asyncapi"
    assert account["name"]
    assert account["type"]      # e.g. COLLECTIVE
    assert account["currency"]  # e.g. USD


def test_graphql_query_rejects_mutation(server):
    """The read-only guard rejects mutations before any network call — core safety property."""
    mutation = 'mutation { createCollective(collective: {name: "x", slug: "x"}) { id } }'
    raised, text = False, ""
    try:
        text = _tool_text(asyncio.run(server.call_tool("graphql_query", {"query": mutation})))
    except Exception as exc:  # ReadOnlyError (or an MCP-wrapped tool error)
        raised, text = True, str(exc)
    assert raised or any(w in text.lower() for w in ("read-only", "mutation", "reject")), (
        f"mutation was not rejected: {text!r}"
    )
