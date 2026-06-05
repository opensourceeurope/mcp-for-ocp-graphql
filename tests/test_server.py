import asyncio
from mcp_for_ocp_graphql.server import build_server
from mcp_for_ocp_graphql.schema_index import SchemaIndex

FIXTURE = {"queryType": {"fields": []}, "types": [
    {"kind": "OBJECT", "name": "Host", "description": "h", "fields": [], "inputFields": None, "enumValues": None}]}

def test_build_server_registers_both_tools():
    mcp = build_server(SchemaIndex(FIXTURE), endpoint="https://oc/graphql", token=None)
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {"graphql_query", "schema_lookup"}
