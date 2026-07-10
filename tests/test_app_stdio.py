from mcp_for_ocp_graphql.app_stdio import resolve_token, load_doc_search

def test_resolve_token_reads_env():
    assert resolve_token({"OC_PERSONAL_TOKEN": "abc"}) == "abc"

def test_resolve_token_none_when_absent():
    assert resolve_token({}) is None

def test_resolve_token_none_when_empty_string():
    assert resolve_token({"OC_PERSONAL_TOKEN": ""}) is None

def test_load_doc_search_is_callable():
    assert callable(load_doc_search)

def test_load_doc_search_returns_none_or_doc_search_instance():
    """load_doc_search returns None if the index is missing, or a DocSearch if the baked index exists."""
    from mcp_for_ocp_graphql.search import DocSearch
    result = load_doc_search()
    assert result is None or isinstance(result, DocSearch)
