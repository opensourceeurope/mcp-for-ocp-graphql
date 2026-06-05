# mcp-for-ocp-graphql — Agent Instructions

A Python MCP server for the [Open Collective GraphQL API v2](https://api.opencollective.com/graphql/v2). It exposes **three tools** — `search_docs`, `schema_lookup`, `graphql_query` — that let an assistant learn the schema and docs, then run **read-only** queries. Mutations and subscriptions are rejected. Published to PyPI; run via `uvx mcp-for-ocp-graphql`. Python ≥3.11, MIT-licensed.

## Authorship Rules

- **NEVER add `Co-Authored-By:` with yourself (an agent) as a co-author of any commit.** Agents are assistants and tools — they are not authors. Only humans can be authors of commits.
- AI assistance disclosure belongs in the pull request description using the exact format below — not in commit authorship metadata:
  ```
  Generated-by: <Agent Name and Version> following [AI Policy](https://github.com/opensourceeurope/.github/blob/main/AI-POLICY.md)
  ```

## Commit Conventions

- Use conventional commits: `feat:`, `fix:`, `docs:`, `ci:`, `chore:`
- This project is MIT-licensed — do not introduce incompatibly licensed material.

## Running Tests

```bash
uv sync           # install runtime + dev deps from uv.lock
uv run pytest     # run the suite
```

Tests live in `tests/` and use `pytest`. Follow TDD: write the failing test first, watch it fail, then implement.

## Architecture

### Two transports / entry points

Both serve the **same three tools** built by `server.register_tools`; they differ only in how the OC token is supplied.

- **stdio** — console script `mcp-for-ocp-graphql` (`app_stdio.main`). Single user. Token comes from the `OC_PERSONAL_TOKEN` env var and is **optional**: no token → anonymous public-data mode. The token is a plain string passed to the tools.
- **hosted HTTP** — console script `mcp-for-ocp-graphql-http` (`app_http.main`). Streamable HTTP with an OAuth 2.1 / PKCE passthrough. Each user pastes their own OC personal token into the browser form at `/oc-login`; that token becomes the OAuth bearer and is read per-request from the auth context and forwarded as the `Personal-Token` header. `OC_PERSONAL_TOKEN` is **not** used here. Env: `PORT` (default 3000), `PUBLIC_URL` (OAuth issuer; https in prod), `OC_GRAPHQL_ENDPOINT`. Deployed via the Docker image (Scaleway/OVH/Hetzner).

### Module map

| Module | Responsibility |
|---|---|
| `graphql.py` | `read_only()` query-op check + `execute_query()` HTTP proxy to the OC endpoint. Rejects non-query ops (`ReadOnlyError`). |
| `schema_index.py` | `SchemaIndex` — loads the introspected schema, `lookup()`/`search()` by name, renders type refs. `format_lookup()` for the tool output. |
| `schema_fetch.py` | Introspects the live OC API and writes `data/schema.json` (run as `python -m ...schema_fetch`). |
| `schema_ref.py` | Renders an introspection schema as markdown (the schema-reference corpus source). |
| `server.py` | `register_tools()` / `build_server()` — wires the three tools onto a `FastMCP`. `resolve_call_token()` allows a per-call callable token. |
| `app_stdio.py` | stdio entry point: loads baked schema + docs index, resolves env token, runs FastMCP over stdio. |
| `app_http.py` | hosted HTTP entry point: builds the Starlette app, OAuth provider, `/oc-login` routes, per-request token from auth context. |
| `auth.py` | `OCAuthProvider` (OAuth 2.1 authorization server), `verify_oc_token()`, `render_auth_form()`, single-use short-TTL auth codes. |
| `embedding.py` | Sentence-Transformers embedder (`nomic-embed-text-v1.5`) with the nomic `search_query:` prefix. |
| `search.py` | `DocSearch` — Milvus Lite client wrapping the baked vector index for `search_docs`. |
| `indexer.py` | Build-time: loads OpenCrane `chunks.json` + `embeddings.json` into a Milvus Lite collection. |

### The three tools (learn, then execute)

1. `search_docs(query, top_k=5)` — semantic search over the baked docs/schema-reference index. Use **first**.
2. `schema_lookup(name)` — exact type/query-field definition incl. args (name, type, required, default); substring matches return candidates.
3. `graphql_query(query, variables=None)` — read-only proxy; every operation parsed and required to be a `query`, else rejected.

### RAG build pipeline (build-time only)

The docs index is built **at build time**, never at runtime:

- The OpenCrane CLI (`uvx opencrane`) runs `llms` / `chunk` / `embed` over the corpus in `corpus/sources/` — the six OC GraphQL guides (from `github.com/opencollective/graphql-docs-v2`), a generated schema reference, and the querying skill — producing `.opencrane/chunks.json` (committed, reproducible input) and `.opencrane/embeddings.json` (gitignored).
- **Our own `indexer.py`** then loads those chunks + embeddings into a Milvus Lite collection at `data/milvus.db/`. We do **not** use OpenCrane's MCP server — OpenCrane is a build-time CLI only, and we index into Milvus ourselves.
- `data/milvus.db/` and `data/schema.json` are baked into the wheel (gitignored in source). CI bakes them on the runner before `docker build`.

## Key Decisions — Do Not Quietly Undo

- **Read-only proxy.** `graphql_query` parses the document and rejects anything that is not a `query` operation (mutations, subscriptions). This is the core safety property — do not relax it.
- **`OC_PERSONAL_TOKEN` is stdio-only.** The HTTP server gets each user's token via OAuth and forwards it per-request; it must never read a shared `OC_PERSONAL_TOKEN`.
- **Token may be absent (stdio).** No token → anonymous public-data mode. Do not make the token mandatory for stdio.
- **Presence-only access-token verification.** In HTTP mode, the OAuth provider checks only that a bearer string is present per request — it does not re-call OC on every request. The token is validated exactly once, at form-submit time (`verify_oc_token` → `{ me { id } }`). OC rejects bad tokens naturally when a tool runs.
- **Never log or persist tokens.** The personal token / `Personal-Token` value must never appear in logs, error messages, or stack traces, and is not cached server-side. Log operation names and status codes, not headers or bodies.
- **OpenCrane is build-time only.** The RAG corpus pipeline runs at build time via the CLI; the server depends only on the baked `milvus.db/`. Do not add a runtime dependency on OpenCrane or its MCP.
- **Milvus Lite is baked, not a server.** `search.py` opens the baked `data/milvus.db/` file directly; there is no separate Milvus server to run or connect to.
- **XSS escaping in `auth.py`.** Every user-controlled value rendered into the login form HTML must be escaped (`html.escape`). The auth form is a security boundary.
