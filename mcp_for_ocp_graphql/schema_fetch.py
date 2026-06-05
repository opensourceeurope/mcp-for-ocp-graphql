import json
import sys
from pathlib import Path
import httpx

INTROSPECTION_QUERY = """{
  __schema {
    queryType {
      fields {
        name
        description
        args { name description defaultValue type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
        type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
      }
    }
    types {
      kind
      name
      description
      fields(includeDeprecated: false) {
        name
        description
        args { name defaultValue type { kind name ofType { kind name ofType { kind name } } } }
        type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
      }
      inputFields { name description defaultValue type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
      enumValues { name }
    }
  }
}"""

DEFAULT_ENDPOINT = "https://api.opencollective.com/graphql/v2"


def fetch_schema(endpoint: str, *, client) -> dict:
    response = client.post(endpoint, json={"query": INTROSPECTION_QUERY},
                           headers={"Content-Type": "application/json"})
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError("Introspection errors: " + ", ".join(e["message"] for e in payload["errors"]))
    schema = (payload.get("data") or {}).get("__schema")
    if not schema:
        raise RuntimeError("Introspection succeeded but response contained no schema data")
    return schema


def main():
    endpoint = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ENDPOINT
    out = Path(__file__).parent / "data" / "schema.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60) as client:
        schema = fetch_schema(endpoint, client=client)
    out.write_text(json.dumps(schema))
    sys.stderr.write(f"Wrote {out} — {len(schema['queryType']['fields'])} queries, {len(schema['types'])} types\n")


if __name__ == "__main__":
    main()
