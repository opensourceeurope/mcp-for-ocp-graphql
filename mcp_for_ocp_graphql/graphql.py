import httpx
from graphql import parse, OperationType, OperationDefinitionNode


def read_only(query: str) -> bool:
    """True only if every operation in the document is a query. Raises GraphQLSyntaxError on parse failure."""
    document = parse(query)
    operations = [d for d in document.definitions if isinstance(d, OperationDefinitionNode)]
    if not operations:
        return False
    return all(op.operation == OperationType.QUERY for op in operations)


class ReadOnlyError(ValueError):
    """Raised when a non-query (mutation/subscription) operation is submitted."""


class GraphQLHTTPError(httpx.HTTPStatusError):
    """Non-2xx response, with the API's own GraphQL error messages kept in the message.

    Subclasses httpx.HTTPStatusError so existing `except httpx.HTTPStatusError` still catches it.
    """


_BODY_EXCERPT_LIMIT = 500


def error_messages(response) -> list[str]:
    """The `errors[].message` strings from a GraphQL response body; empty if the body has none."""
    try:
        payload = response.json()
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return []
    return [str(e["message"]) for e in errors if isinstance(e, dict) and e.get("message")]


def _raise_for_status(response, endpoint):
    """Raise GraphQLHTTPError naming the invalid fields, instead of a bare status code.

    The OC API answers a malformed query with 400 and an `errors[]` array that names the
    offending field or argument; httpx's raise_for_status() discards that body, which turns
    one bad guess into several blind retries.
    """
    if not response.is_error:
        return
    summary = f"{response.status_code} {response.reason_phrase} from {endpoint}"
    details = error_messages(response)
    if details:
        summary = f"{summary}: " + "; ".join(details)
    else:
        body = response.text.strip()
        if body:
            excerpt = body[:_BODY_EXCERPT_LIMIT]
            if len(body) > _BODY_EXCERPT_LIMIT:
                excerpt += "…"
            summary = f"{summary}: {excerpt}"
    raise GraphQLHTTPError(summary, request=response.request, response=response)


def execute_query(query, variables=None, *, endpoint, token, client):
    """Validate read-only, then POST the query to the OC GraphQL endpoint and return the parsed JSON."""
    if not read_only(query):
        raise ReadOnlyError(
            "Only read-only query operations are allowed; mutations and subscriptions are rejected."
        )
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Personal-Token"] = token
    response = client.post(endpoint, json={"query": query, "variables": variables or {}}, headers=headers)
    _raise_for_status(response, endpoint)
    return response.json()
