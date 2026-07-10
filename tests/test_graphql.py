import pytest
from mcp_for_ocp_graphql.graphql import read_only

def test_read_only_true_for_query():
    assert read_only("{ account(slug: \"x\") { id } }") is True
    assert read_only("query Q { me { id } }") is True

def test_read_only_false_for_mutation():
    assert read_only("mutation { createExpense { id } }") is False

def test_read_only_false_for_subscription():
    assert read_only("subscription { updates { id } }") is False

def test_read_only_false_when_any_operation_is_a_mutation():
    assert read_only("query A { a } mutation B { b }") is False

def test_read_only_raises_on_syntax_error():
    from graphql import GraphQLSyntaxError
    with pytest.raises(GraphQLSyntaxError):
        read_only("{ this is not valid")

import json
import httpx
from mcp_for_ocp_graphql.graphql import execute_query, ReadOnlyError

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_execute_query_posts_and_returns_data():
    captured = {}
    def handler(request):
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"account": {"slug": "demo"}}})
    with _client(handler) as client:
        result = execute_query("{ account(slug:\"demo\") { slug } }", None,
                               endpoint="https://oc/graphql", token="tok", client=client)
    assert result["data"]["account"]["slug"] == "demo"
    assert captured["headers"]["Personal-Token"] == "tok"
    assert captured["body"]["query"].startswith("{ account")

def test_execute_query_omits_token_header_when_absent():
    def handler(request):
        assert "Personal-Token" not in request.headers
        return httpx.Response(200, json={"data": {}})
    with _client(handler) as client:
        execute_query("{ me { id } }", None, endpoint="https://oc/graphql", token=None, client=client)

def test_execute_query_rejects_mutation():
    def handler(request):
        raise AssertionError("network must not be hit for a rejected mutation")
    with _client(handler) as client:
        with pytest.raises(ReadOnlyError):
            execute_query("mutation { x }", None, endpoint="https://oc/graphql", token="t", client=client)

def test_execute_query_raises_on_http_error():
    def handler(request):
        return httpx.Response(500, text="boom")
    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            execute_query("{ me { id } }", None, endpoint="https://oc/graphql", token="t", client=client)
