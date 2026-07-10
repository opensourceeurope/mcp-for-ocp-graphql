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
    response.raise_for_status()
    return response.json()
