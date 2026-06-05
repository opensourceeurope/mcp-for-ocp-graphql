import json
import os
import sys
from importlib.resources import files
from .schema_index import SchemaIndex
from .server import build_server

DEFAULT_ENDPOINT = "https://api.opencollective.com/graphql/v2"


def resolve_token(env=None):
    env = os.environ if env is None else env
    return env.get("OC_PERSONAL_TOKEN") or None


def load_schema() -> dict:
    text = files("mcp_for_ocp_graphql.data").joinpath("schema.json").read_text()
    return json.loads(text)


def main():
    endpoint = os.environ.get("OC_GRAPHQL_ENDPOINT", DEFAULT_ENDPOINT)
    token = resolve_token()
    if not token:
        sys.stderr.write(
            "No OC_PERSONAL_TOKEN set — running anonymously (public data only, OC rate limits apply).\n"
        )
    index = SchemaIndex(load_schema())
    server = build_server(index, endpoint=endpoint, token=token)
    server.run()  # stdio transport (FastMCP default)


if __name__ == "__main__":
    main()
