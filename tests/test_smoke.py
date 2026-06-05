import asyncio
from mcp_for_ocp_graphql.app_stdio import load_schema
from mcp_for_ocp_graphql.schema_index import SchemaIndex, format_lookup
from mcp_for_ocp_graphql.server import build_server

def test_real_schema_loads_and_has_host_query():
    idx = SchemaIndex(load_schema())
    assert "host" in idx.queries
    assert "Host" in idx.types

def test_schema_lookup_describes_host_metrics_arg_bearing_children():
    idx = SchemaIndex(load_schema())
    out = format_lookup(idx, "HostMetricsNamespace")
    assert "hostedCollectivesFinancialActivity" in out
    assert "required" in out

def test_server_lists_two_tools_with_real_schema():
    idx = SchemaIndex(load_schema())
    mcp = build_server(idx, endpoint="https://api.opencollective.com/graphql/v2", token=None)
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"graphql_query", "schema_lookup"}
