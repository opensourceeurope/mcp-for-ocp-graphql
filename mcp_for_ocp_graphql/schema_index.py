import json


def type_str(t) -> str:
    if not t:
        return "Unknown"
    kind = t.get("kind")
    if kind == "NON_NULL":
        return type_str(t.get("ofType")) + "!"
    if kind == "LIST":
        return "[" + type_str(t.get("ofType")) + "]"
    return t.get("name") or "Unknown"


def arg_required(arg) -> bool:
    t = arg.get("type") or {}
    return t.get("kind") == "NON_NULL" and arg.get("defaultValue") is None


class SchemaIndex:
    def __init__(self, schema: dict):
        self.schema = schema
        self.types = {t["name"]: t for t in schema.get("types", []) if t.get("name")}
        self.queries = {f["name"]: f for f in (schema.get("queryType") or {}).get("fields", [])}

    def _args(self, args):
        return [
            {"name": a["name"], "type": type_str(a.get("type")),
             "required": arg_required(a), "default": a.get("defaultValue")}
            for a in (args or [])
        ]

    def search(self, term: str):
        term = term.lower()
        names = {n for n in self.types if term in n.lower()}
        names |= {n for n in self.queries if term in n.lower()}
        return sorted(names)

    def lookup(self, name: str):
        if name in self.queries:
            f = self.queries[name]
            return {"kind": "query", "name": name, "description": f.get("description"),
                    "type": type_str(f.get("type")), "args": self._args(f.get("args"))}
        if name in self.types:
            t = self.types[name]
            return {"kind": t.get("kind"), "name": t.get("name"), "description": t.get("description"),
                    "fields": [{"name": fld["name"], "type": type_str(fld.get("type")),
                                "args": self._args(fld.get("args"))} for fld in (t.get("fields") or [])],
                    "inputFields": [{"name": i["name"], "type": type_str(i.get("type"))}
                                    for i in (t.get("inputFields") or [])],
                    "enumValues": [e["name"] for e in (t.get("enumValues") or [])]}
        return None


def format_lookup(index: "SchemaIndex", name: str) -> str:
    found = index.lookup(name)
    if found is not None:
        return json.dumps(found, indent=2)
    candidates = index.search(name)
    if candidates:
        return f"No exact match for '{name}'. Candidates: {', '.join(candidates[:20])}"
    return f"No type or query field named '{name}'."
