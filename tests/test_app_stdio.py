from mcp_for_ocp_graphql.app_stdio import resolve_token

def test_resolve_token_reads_env():
    assert resolve_token({"OC_PERSONAL_TOKEN": "abc"}) == "abc"

def test_resolve_token_none_when_absent():
    assert resolve_token({}) is None

def test_resolve_token_none_when_empty_string():
    assert resolve_token({"OC_PERSONAL_TOKEN": ""}) is None
