import json
import os
import sys
from importlib.resources import files
from pathlib import Path
from .schema_index import SchemaIndex
from .server import build_server
from .search import DocSearch

DEFAULT_ENDPOINT = "https://api.opencollective.com/graphql/v2"


def resolve_token(env=None):
    env = os.environ if env is None else env
    return env.get("OC_PERSONAL_TOKEN") or None


def load_schema() -> dict:
    text = files("mcp_for_ocp_graphql.data").joinpath("schema.json").read_text()
    return json.loads(text)


def load_doc_search():
    """Return a DocSearch backed by the baked docs.json corpus, or None if it's absent."""
    try:
        path = Path(str(files("mcp_for_ocp_graphql.data").joinpath("docs.json")))
    except Exception:
        return None
    if not path.exists():
        return None
    return DocSearch(str(path))


def main():
    endpoint = os.environ.get("OC_GRAPHQL_ENDPOINT", DEFAULT_ENDPOINT)
    token = resolve_token()
    if not token:
        sys.stderr.write(
            "No OC_PERSONAL_TOKEN set — running anonymously (public data only, OC rate limits apply).\n"
        )
    index = SchemaIndex(load_schema())
    doc_search = load_doc_search()
    server = build_server(index, endpoint=endpoint, token=token, doc_search=doc_search)
    server.run()  # stdio transport (FastMCP default)


if __name__ == "__main__":
    main()
