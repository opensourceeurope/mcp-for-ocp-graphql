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


def resolve_call_token(token):
    """Resolve the token to use for a single tool call.

    ``token`` may be a plain string (static, e.g. stdio mode), ``None`` (anonymous),
    or a zero-arg callable (HTTP mode, where the per-request bearer is read from the
    auth context at call time). Callables are invoked here so the value is never
    captured at registration time.
    """
    return token() if callable(token) else token


def register_tools(mcp: FastMCP, *, index: SchemaIndex, endpoint: str, token, doc_search=None, client_factory=None) -> FastMCP:
    """Register the three OC tools (graphql_query, schema_lookup, search_docs) on ``mcp``.

    ``token`` is resolved per call via :func:`resolve_call_token`, so a callable may be
    supplied to forward a per-request token. Returns ``mcp`` for convenience.
    """
    factory = client_factory or (lambda: httpx.Client(timeout=30))

    @mcp.tool()
    def graphql_query(query: str, variables: dict | None = None) -> str:
        """Execute a read-only Open Collective GraphQL v2 query and return the JSON result.
        Mutations and subscriptions are rejected. Before querying, use search_docs to find the
        right queries/fields, then schema_lookup to confirm their exact fields, args, and types.

        Personal data — STOP and ask before fetching. Some fields return PII (email/emails,
        phoneNumber, address, legalName, and anything under payoutMethod/paymentMethod/location
        on Individual accounts). NEVER put these in a query — not by default, not inside a wider
        selection, and NOT even when the user's request seems to call for them — until you have:
        (1) told the user plainly that the data will enter the model's context (a hosted model
        transmits it to its provider) and that anything you then write it to is a further
        disclosure, and (2) received their explicit confirmation for THAT request. If a request
        would need PII, do not silently run it: surface the warning, then wait for an explicit
        yes before including the field."""
        call_token = resolve_call_token(token)
        with factory() as client:
            data = execute_query(query, variables, endpoint=endpoint, token=call_token, client=client)
        return json.dumps(data, indent=2)

    @mcp.tool()
    def schema_lookup(name: str) -> str:
        """Look up the exact definition of a GraphQL type or query field by name:
        its description, fields, and arguments (name, type, required, default). Substring matches return candidates."""
        return format_lookup(index, name)

    @mcp.tool()
    def search_docs(query: str, top_k: int = 5) -> str:
        """Keyword search over Open Collective GraphQL docs + query-field reference.
        Use this FIRST to learn which fields/queries to use, then call graphql_query.
        Returns the most relevant documentation chunks (best matches on your search terms)."""
        return format_search(doc_search, query, top_k)

    return mcp


def build_server(index: SchemaIndex, *, endpoint: str, token, client_factory=None, doc_search=None) -> FastMCP:
    mcp = FastMCP("mcp-for-ocp-graphql")
    return register_tools(
        mcp,
        index=index,
        endpoint=endpoint,
        token=token,
        doc_search=doc_search,
        client_factory=client_factory,
    )
