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

from mcp_for_ocp_graphql.graphql import GraphQLHTTPError


def test_execute_query_surfaces_graphql_error_messages_on_400():
    def handler(request):
        return httpx.Response(400, json={"errors": [
            {"message": 'Cannot query field "totalHostedCollectives" on type "Host".'},
            {"message": 'Unknown argument "dateFrom" on field "Host.metrics".'},
        ]})
    with _client(handler) as client:
        with pytest.raises(GraphQLHTTPError) as excinfo:
            execute_query("{ me { id } }", None, endpoint="https://oc/graphql", token="t", client=client)
    message = str(excinfo.value)
    assert "totalHostedCollectives" in message
    assert 'Unknown argument "dateFrom"' in message
    assert "400" in message


def test_graphql_http_error_is_an_httpx_status_error():
    def handler(request):
        return httpx.Response(400, json={"errors": [{"message": "nope"}]})
    with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            execute_query("{ me { id } }", None, endpoint="https://oc/graphql", token="t", client=client)


def test_execute_query_falls_back_to_body_excerpt_when_not_graphql_shaped():
    def handler(request):
        return httpx.Response(429, text="error code: 1015 rate limited")
    with _client(handler) as client:
        with pytest.raises(GraphQLHTTPError) as excinfo:
            execute_query("{ me { id } }", None, endpoint="https://oc/graphql", token="t", client=client)
    assert "1015" in str(excinfo.value)


def test_execute_query_truncates_a_huge_error_body():
    def handler(request):
        return httpx.Response(502, text="x" * 5000)
    with _client(handler) as client:
        with pytest.raises(GraphQLHTTPError) as excinfo:
            execute_query("{ me { id } }", None, endpoint="https://oc/graphql", token="t", client=client)
    assert len(str(excinfo.value)) < 700
    assert str(excinfo.value).endswith("…")


def test_execute_query_still_returns_body_when_200_carries_errors():
    def handler(request):
        return httpx.Response(200, json={"data": None, "errors": [{"message": "partial"}]})
    with _client(handler) as client:
        result = execute_query("{ me { id } }", None, endpoint="https://oc/graphql", token="t", client=client)
    assert result["errors"][0]["message"] == "partial"
