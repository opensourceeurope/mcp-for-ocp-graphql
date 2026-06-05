# mcp-for-ocp-graphql

An MCP server for the [Open Collective GraphQL API v2](https://api.opencollective.com/graphql/v2). It gives an AI assistant three tools to **learn the schema, search the docs, and run read-only queries** against Open Collective — without exposing any write operations.

Published to [PyPI](https://pypi.org/project/mcp-for-ocp-graphql/) and run with `uvx mcp-for-ocp-graphql`.

## Using with AI safely

Open Collective data includes personally identifiable information (names, emails, payout details, addresses). This server is a **generic read-only GraphQL proxy** — the `graphql_query` tool can select any field the underlying token is allowed to read, so the guardrail against leaking PII is *prompt-level*, not enforced in code.

- Prefer running **locally** (the stdio transport below) so your data and token never leave your machine.
- Prefer **anonymous mode** (no token) when you only need public data — you then only ever see what the public API exposes.
- The bundled querying skill (`corpus/sources/querying-skill.md`, baked into the docs index) is the place where PII handling and safe field-selection guidance live. Keep it as the control point.

Tokens are never logged or persisted by this server.

## Two ways to run

### Local — stdio (single user, via uvx)

Runs entirely on your machine over the MCP stdio transport. A token is **optional**: with no token the server runs anonymously against public data; with a token it can read whatever that token is authorized for.

```bash
# anonymous (public data only)
uvx mcp-for-ocp-graphql

# authenticated — get a token at https://opencollective.com/dashboard/personal-tokens
OC_PERSONAL_TOKEN=oc_xxx uvx mcp-for-ocp-graphql
```

Generic MCP client config:

```json
{
  "mcpServers": {
    "mcp-for-ocp-graphql": {
      "command": "uvx",
      "args": ["mcp-for-ocp-graphql"],
      "env": { "OC_PERSONAL_TOKEN": "oc_xxx" }
    }
  }
}
```

Claude Code:

```bash
claude mcp add mcp-for-ocp-graphql -e OC_PERSONAL_TOKEN=oc_xxx -- uvx mcp-for-ocp-graphql
```

(Omit `-e OC_PERSONAL_TOKEN=...` to run anonymously.)

### Hosted — Streamable HTTP + OAuth (multi-user, via Docker)

The hosted server speaks MCP over Streamable HTTP and implements an OAuth 2.1 / PKCE **passthrough**: each user opens a browser form at `/oc-login` and pastes their own Open Collective personal token. That token becomes the OAuth access token and is forwarded to the OC API as the `Personal-Token` header on each query. The server mints no tokens of its own and stores no shared credentials.

```bash
docker build -t mcp-for-ocp-graphql .

# default port 3000
docker run -d --name oc-mcp -p 3000:3000 \
  -e PUBLIC_URL=https://your-host \
  mcp-for-ocp-graphql

# custom port
docker run -d --name oc-mcp -p 8080:8080 \
  -e PORT=8080 \
  -e PUBLIC_URL=https://your-host \
  mcp-for-ocp-graphql
```

`PUBLIC_URL` is the publicly reachable URL of the server; it is used as the OAuth issuer and in the auth discovery metadata. **It must use `https://` in production** — OAuth 2.1 rejects non-localhost endpoints over plain HTTP.

Register with Claude Code:

```bash
claude mcp add --transport http mcp-for-ocp-graphql https://your-host/mcp
```

The client prompts for OAuth on first use; a browser opens the token form. Each user authenticates independently — no shared token lives on the server.

Runs on any EU container platform: Scaleway Serverless Containers (free tier), OVH, Hetzner. See [`docs/scaleway-deployment.md`](docs/scaleway-deployment.md) for a step-by-step Scaleway walkthrough.

## The three tools

The intended flow is **learn, then execute**:

1. **`search_docs(query, top_k=5)`** — semantic search over a baked index of the Open Collective GraphQL guides plus a generated schema reference. Use this **first** to figure out which queries and fields you need.
2. **`schema_lookup(name)`** — exact definition of a GraphQL type or query field: its description, fields, and arguments (name, type, required, default). Substring matches return candidate names.
3. **`graphql_query(query, variables=None)`** — execute a read-only GraphQL query and return the JSON result. **Mutations and subscriptions are rejected**: every operation in the document is parsed and must be a `query`.

There are no per-operation typed tools — `graphql_query` is a single generic proxy, which is why the docs index and querying skill carry the field-selection and PII guidance.

## Configuration

| Env var | Default | Used by | Description |
|---|---|---|---|
| `OC_PERSONAL_TOKEN` | _(unset → anonymous)_ | stdio | Open Collective personal token. Optional; not used by the HTTP server (which gets the token via OAuth). |
| `OC_GRAPHQL_ENDPOINT` | `https://api.opencollective.com/graphql/v2` | both | OC GraphQL API endpoint. |
| `PORT` | `3000` | HTTP | HTTP listen port. |
| `PUBLIC_URL` | `http://localhost:<PORT>` | HTTP | Publicly reachable server URL; OAuth 2.1 issuer. **Must be `https://` in production.** |
| `EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | build/search | Sentence-Transformers model used to embed the docs corpus and search queries. Currently fixed in `embedding.py` (`MODEL_NAME`); the corpus index and query embedder must use the same model. |

## Development

```bash
uv sync            # install runtime + dev deps from uv.lock
uv run pytest      # run the test suite
uvx mcp-for-ocp-graphql   # run the stdio server locally
```

### Regenerating the baked data

The wheel ships two baked artifacts under `mcp_for_ocp_graphql/data/` (both gitignored in source, baked at build time):

- **`schema.json`** — the introspected OC schema, used by `schema_lookup`. Regenerate with:
  ```bash
  python -m mcp_for_ocp_graphql.schema_fetch
  ```
- **`milvus.db/`** — a [Milvus Lite](https://milvus.io/docs/milvus_lite.md) vector index of the docs corpus, used by `search_docs`. It is built from the OpenCrane RAG pipeline:
  ```bash
  uvx opencrane embed          # produces .opencrane/embeddings.json
  python -m mcp_for_ocp_graphql.indexer   # loads chunks + embeddings into milvus.db
  ```
  The committed, reproducible input is `.opencrane/chunks.json`. `embeddings.json` and the build logs are regenerated and gitignored.

The corpus itself (`corpus/sources/`) is the six Open Collective GraphQL guides from [opencollective/graphql-docs-v2](https://github.com/opencollective/graphql-docs-v2), a generated schema reference, and the querying skill. CI bakes `schema.json` and `milvus.db/` on the runner *before* `docker build`, so the image never re-downloads the embedding model.

## Stack & credits

- [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP)
- [graphql-core](https://github.com/graphql-python/graphql-core) — read-only query parsing/validation
- [httpx](https://www.python-httpx.org/) — GraphQL transport
- [Milvus Lite](https://milvus.io/) + [Sentence-Transformers](https://www.sbert.net/) (`nomic-embed-text-v1.5`) — docs search
- OpenCrane CLI (`uvx opencrane`) — build-time RAG corpus pipeline (`llms` / `chunk` / `embed`)
- [Open Collective GraphQL API v2](https://developers.opencollective.com/access)

MIT licensed.
