import asyncio
import json
from mcp_for_ocp_graphql.server import build_server, format_search
from mcp_for_ocp_graphql.schema_index import SchemaIndex

FIXTURE = {"queryType": {"fields": []}, "types": [
    {"kind": "OBJECT", "name": "Host", "description": "h", "fields": [], "inputFields": None, "enumValues": None}]}


def test_build_server_registers_three_tools():
    mcp = build_server(SchemaIndex(FIXTURE), endpoint="https://oc/graphql", token=None)
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"graphql_query", "schema_lookup", "search_docs"}


def test_format_search_returns_unavailable_when_doc_search_is_none():
    result = format_search(None, "some query", 5)
    assert result == "Docs search is unavailable (no index loaded)."


def test_format_search_returns_json_from_doc_search():
    class FakeDocSearch:
        def search(self, query, top_k):
            return [{"text": "hi", "source": "x.md", "score": 0.1}]

    result = format_search(FakeDocSearch(), "my query", 5)
    parsed = json.loads(result)
    assert parsed == [{"text": "hi", "source": "x.md", "score": 0.1}]


def _tool_text(result) -> str:
    """Extract plain text from an MCP call_tool result.
    call_tool returns a tuple of (list[TextContent], dict); we want the first TextContent's text.
    """
    content_list = result[0]  # first element of tuple is the list of content items
    item = content_list[0]
    if hasattr(item, "text"):
        return item.text
    return str(item)


def test_search_docs_tool_uses_doc_search():
    """Verify the registered search_docs tool delegates to format_search with a fake DocSearch."""
    class FakeDocSearch:
        def __init__(self):
            self.called_with = None

        def search(self, query, top_k):
            self.called_with = (query, top_k)
            return [{"text": "expense result", "source": "expenses.md", "score": 0.9}]

    fake = FakeDocSearch()
    mcp = build_server(SchemaIndex(FIXTURE), endpoint="https://oc/graphql", token=None, doc_search=fake)

    # Get the registered tools and find search_docs
    tools = asyncio.run(mcp.list_tools())
    tool_names = {t.name for t in tools}
    assert "search_docs" in tool_names

    # Call the tool directly through MCP's call mechanism
    result = asyncio.run(mcp.call_tool("search_docs", {"query": "list expenses", "top_k": 3}))
    parsed = json.loads(_tool_text(result))
    assert parsed == [{"text": "expense result", "source": "expenses.md", "score": 0.9}]
    assert fake.called_with == ("list expenses", 3)


def test_search_docs_tool_returns_unavailable_when_no_doc_search():
    mcp = build_server(SchemaIndex(FIXTURE), endpoint="https://oc/graphql", token=None)
    result = asyncio.run(mcp.call_tool("search_docs", {"query": "anything"}))
    assert _tool_text(result) == "Docs search is unavailable (no index loaded)."
