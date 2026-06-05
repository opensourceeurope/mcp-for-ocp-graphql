import json
import httpx
from mcp.server.fastmcp import FastMCP
from .graphql import execute_query
from .schema_index import SchemaIndex, format_lookup


def build_server(index: SchemaIndex, *, endpoint: str, token, client_factory=None) -> FastMCP:
    factory = client_factory or (lambda: httpx.Client(timeout=30))
    mcp = FastMCP("mcp-for-ocp-graphql")

    @mcp.tool()
    def graphql_query(query: str, variables: dict | None = None) -> str:
        """Execute a read-only Open Collective GraphQL v2 query and return the JSON result.
        Mutations and subscriptions are rejected. Use schema_lookup to find fields/args first."""
        with factory() as client:
            data = execute_query(query, variables, endpoint=endpoint, token=token, client=client)
        return json.dumps(data, indent=2)

    @mcp.tool()
    def schema_lookup(name: str) -> str:
        """Look up the exact definition of a GraphQL type or query field by name:
        its description, fields, and arguments (name, type, required, default). Substring matches return candidates."""
        return format_lookup(index, name)

    return mcp
