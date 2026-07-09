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


def test_queries_only_omits_type_sections():
    """queries_only=True keeps the query fields but drops the per-type field dump."""
    full = schema_to_markdown(FIXTURE)
    slim = schema_to_markdown(FIXTURE, queries_only=True)
    # query field is still present
    assert "collective" in slim
    assert "# Query Fields" in slim
    # the "# Types" dump (e.g. the Collective/CollectiveInput type sections) is gone
    assert "# Types" in full and "# Types" not in slim
    assert "CollectiveInput" in full and "CollectiveInput" not in slim
    assert len(slim) < len(full)


def test_main_queries_only_writes_one_file_per_query(tmp_path, monkeypatch):
    """--queries-only DIR writes one <query>.md per top-level query field."""
    import mcp_for_ocp_graphql.schema_ref as sr
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "schema.json").write_text(json.dumps(FIXTURE))
    monkeypatch.setattr(sr, "__file__", str(tmp_path / "schema_ref.py"))
    out_dir = tmp_path / "local"
    main(["--queries-only", str(out_dir)])
    # FIXTURE has one query field: collective
    files = sorted(p.name for p in out_dir.glob("*.md"))
    assert files == ["collective.md"]
    text = (out_dir / "collective.md").read_text()
    assert text.startswith("# `collective` query")
    assert "Returns `Collective`." in text
    # no per-type dump leaked into the query file
    assert "CollectiveInput" not in text


def test_write_query_field_files_removes_stale(tmp_path):
    """Stale .md files from a previous run are cleared before writing."""
    from mcp_for_ocp_graphql.schema_ref import write_query_field_files
    out_dir = tmp_path / "local"
    out_dir.mkdir()
    (out_dir / "gone.md").write_text("stale")
    n = write_query_field_files(FIXTURE, out_dir)
    assert n == 1
    assert not (out_dir / "gone.md").exists()
    assert (out_dir / "collective.md").exists()


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
