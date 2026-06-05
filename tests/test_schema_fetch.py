import pytest
import httpx
from mcp_for_ocp_graphql.schema_fetch import fetch_schema, INTROSPECTION_QUERY

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))

def test_introspection_query_captures_nested_arg_name_and_default():
    assert "args { name defaultValue type {" in INTROSPECTION_QUERY

def test_fetch_schema_returns_schema_object():
    def handler(request):
        return httpx.Response(200, json={"data": {"__schema": {"queryType": {"fields": []}, "types": []}}})
    with _client(handler) as client:
        schema = fetch_schema("https://oc/graphql", client=client)
    assert "types" in schema and "queryType" in schema

def test_fetch_schema_does_not_send_token_header():
    def handler(request):
        assert "Personal-Token" not in request.headers
        return httpx.Response(200, json={"data": {"__schema": {"queryType": {"fields": []}, "types": []}}})
    with _client(handler) as client:
        fetch_schema("https://oc/graphql", client=client)

def test_fetch_schema_raises_on_graphql_errors():
    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": "nope"}]})
    with _client(handler) as client:
        with pytest.raises(RuntimeError, match="nope"):
            fetch_schema("https://oc/graphql", client=client)
