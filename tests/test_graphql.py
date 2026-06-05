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
