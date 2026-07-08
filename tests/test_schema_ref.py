"""TDD tests for schema_ref.schema_to_markdown."""
import json

from mcp_for_ocp_graphql.schema_ref import main, schema_to_markdown


def nn(of):
    return {"kind": "NON_NULL", "name": None, "ofType": of}


def scalar(name):
    return {"kind": "SCALAR", "name": name, "ofType": None}


def inp(name):
    return {"kind": "INPUT_OBJECT", "name": name, "ofType": None}


FIXTURE = {
    "queryType": {
        "fields": [
            {
                "name": "collective",
                "description": "Returns a collective.",
                "args": [
                    {"name": "slug", "defaultValue": None, "type": scalar("String")},
                    {"name": "id", "defaultValue": None, "type": nn(scalar("Int"))},
                ],
                "type": {"kind": "OBJECT", "name": "Collective", "ofType": None},
            }
        ]
    },
    "types": [
        {
            "kind": "OBJECT",
            "name": "Collective",
            "description": "A collective entity.",
            "fields": [
                {"name": "slug", "args": [], "type": scalar("String")},
                {
                    "name": "members",
                    "args": [
                        {"name": "limit", "defaultValue": "10", "type": nn(scalar("Int"))}
                    ],
                    "type": {"kind": "OBJECT", "name": "MemberCollection", "ofType": None},
                },
            ],
            "inputFields": None,
            "enumValues": None,
        },
        {
            "kind": "INPUT_OBJECT",
            "name": "CollectiveInput",
            "description": "Input for collective queries.",
            "fields": None,
            "inputFields": [
                {"name": "slug", "type": scalar("String")},
                {"name": "id", "type": nn(scalar("Int"))},
            ],
            "enumValues": None,
        },
        # SCALAR types should NOT appear as sections
        {
            "kind": "SCALAR",
            "name": "String",
            "description": "Built-in string scalar.",
            "fields": None,
            "inputFields": None,
            "enumValues": None,
        },
    ],
}


def test_query_field_section_present():
    md = schema_to_markdown(FIXTURE)
    assert "collective" in md


def test_type_section_present():
    md = schema_to_markdown(FIXTURE)
    assert "Collective" in md


def test_arg_rendered_as_name_colon_type():
    md = schema_to_markdown(FIXTURE)
    assert "slug: String" in md


def test_required_arg_marked():
    """NON_NULL arg with no default must show '(required)'."""
    md = schema_to_markdown(FIXTURE)
    # 'id' in the collective query is NON_NULL with no default → required
    assert "(required)" in md


def test_optional_arg_not_marked_required():
    """slug is SCALAR (not NON_NULL), so it should NOT be marked required."""
    md = schema_to_markdown(FIXTURE)
    # Find the slug line and check it doesn't carry (required)
    lines_with_slug = [l for l in md.splitlines() if "slug: String" in l]
    assert lines_with_slug, "slug: String line not found"
    # At least one slug line should NOT have (required) — the scalar one
    assert any("(required)" not in l for l in lines_with_slug)


def test_input_object_section_present():
    md = schema_to_markdown(FIXTURE)
    assert "CollectiveInput" in md


def test_scalar_type_not_a_section():
    """SCALAR types should not get their own heading section."""
    md = schema_to_markdown(FIXTURE)
    # String is a scalar; it should not appear as a heading
    headings = [l for l in md.splitlines() if l.startswith("#") and "String" in l]
    assert not headings, f"Scalar String unexpectedly got a heading: {headings}"


def test_main_writes_reference_from_baked_schema(tmp_path, monkeypatch):
    """`main` reads data/schema.json and writes the rendered markdown to OUTPUT."""
    import mcp_for_ocp_graphql.schema_ref as sr

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "schema.json").write_text(json.dumps(FIXTURE))
    monkeypatch.setattr(sr, "__file__", str(tmp_path / "schema_ref.py"))

    out = tmp_path / "nested" / "schema-reference.md"
    main([str(out)])

    assert out.exists()
    assert "collective" in out.read_text()
