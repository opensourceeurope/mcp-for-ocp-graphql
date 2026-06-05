from graphql import parse, OperationType
from graphql.language.ast import OperationDefinitionNode


def read_only(query: str) -> bool:
    """True only if every operation in the document is a query. Raises GraphQLSyntaxError on parse failure."""
    document = parse(query)
    operations = [d for d in document.definitions if isinstance(d, OperationDefinitionNode)]
    if not operations:
        return False
    return all(op.operation == OperationType.QUERY for op in operations)
