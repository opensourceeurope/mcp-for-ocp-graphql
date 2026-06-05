import json
import httpx
from mcp.server.fastmcp import FastMCP
from .graphql import execute_query
from .schema_index import SchemaIndex, format_lookup


def format_search(doc_search, query: str, top_k: int) -> str:
    """Helper: run doc_search.search and return JSON, or the unavailable message if doc_search is None."""
    if doc_search is None:
        return "Docs search is unavailable (no index loaded)."
    hits = doc_search.search(query, top_k=top_k)
    return json.dumps(hits, indent=2)


def build_server(index: SchemaIndex, *, endpoint: str, token, client_factory=None, doc_search=None) -> FastMCP:
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

    @mcp.tool()
    def search_docs(query: str, top_k: int = 5) -> str:
        """Semantic search over Open Collective GraphQL docs + schema reference.
        Use this FIRST to learn which fields/queries to use, then call graphql_query.
        Returns the most relevant documentation chunks."""
        return format_search(doc_search, query, top_k)

    return mcp
