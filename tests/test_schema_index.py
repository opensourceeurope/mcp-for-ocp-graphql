from mcp_for_ocp_graphql.schema_index import type_str, arg_required, SchemaIndex, format_lookup

def nn(of): return {"kind": "NON_NULL", "name": None, "ofType": of}
def scalar(name): return {"kind": "SCALAR", "name": name, "ofType": None}
def inp(name): return {"kind": "INPUT_OBJECT", "name": name, "ofType": None}

FIXTURE = {
    "queryType": {"fields": [
        {"name": "host", "description": "A host", "args": [
            {"name": "slug", "defaultValue": None, "type": scalar("String")}],
         "type": {"kind": "OBJECT", "name": "Host", "ofType": None}},
    ]},
    "types": [
        {"kind": "OBJECT", "name": "Host", "description": "A fiscal host", "fields": [
            {"name": "slug", "args": [], "type": scalar("String")},
            {"name": "communityStats", "args": [
                {"name": "host", "defaultValue": None, "type": nn(inp("AccountReferenceInput"))}],
             "type": {"kind": "OBJECT", "name": "CommunityStats", "ofType": None}},
            {"name": "members", "args": [
                {"name": "limit", "defaultValue": "10", "type": nn(scalar("Int"))}],
             "type": {"kind": "OBJECT", "name": "MemberCollection", "ofType": None}},
        ], "inputFields": None, "enumValues": None},
    ],
}

def test_type_str_renders_wrappers():
    assert type_str(nn(scalar("String"))) == "String!"
    assert type_str({"kind": "LIST", "name": None, "ofType": nn(scalar("Int"))}) == "[Int!]"

def test_arg_required_only_when_non_null_and_no_default():
    assert arg_required({"type": nn(scalar("Int")), "defaultValue": None}) is True
    assert arg_required({"type": nn(scalar("Int")), "defaultValue": "10"}) is False
    assert arg_required({"type": scalar("Int"), "defaultValue": None}) is False

def test_lookup_query_field_returns_args():
    idx = SchemaIndex(FIXTURE)
    found = idx.lookup("host")
    assert found["kind"] == "query"
    assert found["type"] == "Host"
    assert found["args"][0]["name"] == "slug"

def test_lookup_type_reports_field_arg_requiredness():
    idx = SchemaIndex(FIXTURE)
    host = idx.lookup("Host")
    cs = next(f for f in host["fields"] if f["name"] == "communityStats")
    assert cs["args"][0] == {"name": "host", "type": "AccountReferenceInput!", "required": True, "default": None}
    members = next(f for f in host["fields"] if f["name"] == "members")
    assert members["args"][0]["required"] is False

def test_search_substring_over_names():
    idx = SchemaIndex(FIXTURE)
    assert "Host" in idx.search("host")

def test_format_lookup_exact_miss_offers_candidates():
    idx = SchemaIndex(FIXTURE)
    out = format_lookup(idx, "hos")
    assert "Candidates" in out and "Host" in out

def test_format_lookup_total_miss():
    idx = SchemaIndex(FIXTURE)
    assert "No type or query field" in format_lookup(idx, "zzz")
