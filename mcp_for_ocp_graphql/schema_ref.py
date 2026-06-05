"""Render a GraphQL introspection schema as human-readable markdown.

One section per query field and per named OBJECT / INPUT_OBJECT type.
Reuses `type_str` and `arg_required` from schema_index so the rendering is
consistent with the rest of the package.
"""
from .schema_index import type_str, arg_required

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


def schema_to_markdown(schema: dict) -> str:
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
