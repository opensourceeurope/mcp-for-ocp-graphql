"""Render a GraphQL introspection schema as human-readable markdown.

One section per query field and per named OBJECT / INPUT_OBJECT type.
Reuses `type_str` and `arg_required` from schema_index so the rendering is
consistent with the rest of the package.

Run as a module to (re)generate the corpus reference from the baked schema:

    python -m mcp_for_ocp_graphql.schema_ref [OUTPUT_MD]          # full reference, one file
    python -m mcp_for_ocp_graphql.schema_ref --queries-only [DIR] # one file per query field

Reads ``mcp_for_ocp_graphql/data/schema.json`` (produced by ``schema_fetch``).
``--queries-only`` writes one markdown file per top-level query field into ``DIR``
(default ``.opencrane/sources/local``) so OpenCrane pages and chunks each query
separately (one file = one page = focused chunks), instead of one giant blob.
"""
import json
import sys
from pathlib import Path

from .schema_index import type_str, arg_required

DEFAULT_OUTPUT = ".opencrane/sources/local/schema-reference.md"
DEFAULT_QUERIES_DIR = ".opencrane/sources/local"

# Type kinds that get their own reference section.
_SECTION_KINDS = {"OBJECT", "INPUT_OBJECT"}


def _render_arg(arg: dict) -> str:
    name = arg.get("name", "")
    t = type_str(arg.get("type"))
    required = arg_required(arg)
    suffix = " (required)" if required else ""
    return f"  - `{name}: {t}`{suffix}"


def _render_args(args: list) -> list[str]:
    if not args:
        return []
    lines = ["  **Args:**"]
    for a in args:
        lines.append(_render_arg(a))
    return lines


def query_field_doc(field: dict) -> str:
    """Render ONE top-level query field as a standalone markdown document.

    Used to emit one file per query so OpenCrane pages/chunks each separately.
    Arguments are rendered as a single prose sentence (NOT a bullet list): the
    chunker splits markdown lists into one chunk *per item*, which would explode
    each query into dozens of one-arg chunks. Prose keeps the whole query — name,
    return type, and all arg names — in one focused, searchable chunk.
    """
    name = field.get("name", "")
    ret_type = type_str(field.get("type"))
    description = (field.get("description") or "").strip()
    lines = [f"# `{name}` query", "", f"Returns `{ret_type}`.", ""]
    if description:
        lines += [description, ""]
    args = field.get("args") or []
    if args:
        rendered = ", ".join(
            f"`{a.get('name', '')}` ({type_str(a.get('type'))}"
            + (", required)" if arg_required(a) else ")")
            for a in args
        )
        lines.append(f"Arguments: {rendered}.")
    else:
        lines.append("Takes no arguments.")
    lines.append("")
    return "\n".join(lines)


def write_query_field_files(schema: dict, out_dir) -> int:
    """Write one ``<query>.md`` per top-level query field into ``out_dir``.

    Removes stale ``*.md`` in ``out_dir`` first so removed queries don't linger.
    Returns the number of files written.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.md"):
        stale.unlink()
    query_fields = (schema.get("queryType") or {}).get("fields") or []
    for field in query_fields:
        name = field.get("name", "")
        if not name:
            continue
        (out_dir / f"{name}.md").write_text(query_field_doc(field))
    return len(query_fields)


def schema_to_markdown(schema: dict, *, queries_only: bool = False) -> str:
    """Render the schema to markdown.

    queries_only=True emits just the top-level query fields (the "what can I ask
    for" entry-point map) and skips the per-type field dump — a high-signal,
    low-noise slice for the semantic search corpus. schema_lookup still serves the
    full per-type detail on demand from schema.json.
    """
    sections: list[str] = []

    # ── Query fields ──────────────────────────────────────────────────────────
    query_type = schema.get("queryType") or {}
    query_fields = query_type.get("fields") or []
    if query_fields:
        sections.append("# Query Fields\n")
        for field in query_fields:
            name = field.get("name", "")
            description = field.get("description") or ""
            ret_type = type_str(field.get("type"))
            lines = [f"## `{name}` → `{ret_type}`\n"]
            if description:
                lines.append(f"{description}\n")
            arg_lines = _render_args(field.get("args") or [])
            if arg_lines:
                lines.extend(arg_lines)
                lines.append("")
            sections.append("\n".join(lines))

    if queries_only:
        return "\n".join(sections)

    # ── Named types (OBJECT + INPUT_OBJECT only) ───────────────────────────────
    types = schema.get("types") or []
    type_sections: list[str] = []
    for t in types:
        kind = t.get("kind")
        if kind not in _SECTION_KINDS:
            continue
        name = t.get("name", "")
        # Skip internal introspection types
        if name.startswith("__"):
            continue
        description = t.get("description") or ""
        lines = [f"## `{name}` ({kind})\n"]
        if description:
            lines.append(f"{description}\n")

        # OBJECT: has .fields (each field may have args)
        fields = t.get("fields") or []
        if fields:
            lines.append("**Fields:**\n")
            for fld in fields:
                fld_name = fld.get("name", "")
                fld_type = type_str(fld.get("type"))
                lines.append(f"- `{fld_name}: {fld_type}`")
                arg_lines = _render_args(fld.get("args") or [])
                lines.extend(arg_lines)

        # INPUT_OBJECT: has .inputFields
        input_fields = t.get("inputFields") or []
        if input_fields:
            lines.append("**Input fields:**\n")
            for ifld in input_fields:
                ifld_name = ifld.get("name", "")
                ifld_type = type_str(ifld.get("type"))
                required = arg_required(ifld)
                suffix = " (required)" if required else ""
                lines.append(f"- `{ifld_name}: {ifld_type}`{suffix}")

        lines.append("")
        type_sections.append("\n".join(lines))

    if type_sections:
        sections.append("# Types\n")
        sections.extend(type_sections)

    return "\n".join(sections)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    queries_only = False
    if "--queries-only" in argv:
        queries_only = True
        argv.remove("--queries-only")
    schema_path = Path(__file__).parent / "data" / "schema.json"
    schema = json.loads(schema_path.read_text())

    if queries_only:
        out_dir = Path(argv[0]) if argv else Path(DEFAULT_QUERIES_DIR)
        n = write_query_field_files(schema, out_dir)
        sys.stderr.write(f"Wrote {n} query-field files to {out_dir}\n")
        return

    out = Path(argv[0]) if argv else Path(DEFAULT_OUTPUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema_to_markdown(schema))
    sys.stderr.write(f"Wrote {out}\n")


if __name__ == "__main__":
    main()
