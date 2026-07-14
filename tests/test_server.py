import asyncio
import json
from mcp_for_ocp_graphql.server import build_server, format_search, resolve_call_token
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
    With structured output enabled call_tool returns a (list[TextContent], dict) tuple;
    with it disabled it returns the bare list[TextContent]. Handle both, take the first text.
    """
    content_list = result[0] if isinstance(result, tuple) else result
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


def test_resolve_call_token_passthrough_for_str_and_none():
    assert resolve_call_token("static") == "static"
    assert resolve_call_token(None) is None


def test_resolve_call_token_calls_callable():
    assert resolve_call_token(lambda: "dynamic") == "dynamic"


class _CapturingClient:
    """Fake httpx client capturing the Personal-Token header sent to the endpoint."""

    def __init__(self):
        self.sent_token = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, endpoint, json=None, headers=None):
        self.sent_token = (headers or {}).get("Personal-Token")

        class _Resp:
            status_code = 200

            def raise_for_status(self_inner):
                return None

            def json(self_inner):
                return {"data": {"ok": True}}

        return _Resp()


def test_graphql_query_forwards_dynamic_token():
    """A callable token is resolved at call time and forwarded as Personal-Token."""
    captured = _CapturingClient()
    mcp = build_server(
        SchemaIndex(FIXTURE),
        endpoint="https://oc/graphql",
        token=lambda: "dynamic",
        client_factory=lambda: captured,
    )
    result = asyncio.run(mcp.call_tool("graphql_query", {"query": "{ me { id } }"}))
    parsed = json.loads(_tool_text(result))
    assert parsed == {"data": {"ok": True}}
    assert captured.sent_token == "dynamic"


def test_tools_emit_no_structured_content():
    """The tools return plain JSON strings; structured output is disabled so the same
    payload is not duplicated into structuredContent. FastMCP signals this by returning
    the bare content list rather than a (content, structuredContent) tuple."""
    class FakeDocSearch:
        def search(self, query, top_k):
            return [{"text": "hi", "source": "x.md", "score": 0.1}]

    mcp = build_server(SchemaIndex(FIXTURE), endpoint="https://oc/graphql", token=None, doc_search=FakeDocSearch())
    for name, args in [
        ("search_docs", {"query": "x"}),
        ("schema_lookup", {"name": "Host"}),
    ]:
        result = asyncio.run(mcp.call_tool(name, args))
        assert not isinstance(result, tuple), (
            f"{name} should emit no structured content, got a tuple with: {result[1]!r}"
        )
