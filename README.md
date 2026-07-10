# mcp-for-ocp-graphql

An MCP server for the [Open Collective GraphQL API v2](https://api.opencollective.com/graphql/v2). It gives an AI assistant three tools to **learn the schema, search the docs, and run read-only queries** against Open Collective — without exposing any write operations.

Published to [PyPI](https://pypi.org/project/mcp-for-ocp-graphql/) and run with `uvx mcp-for-ocp-graphql`.

## Using with AI safely

Open Collective data includes personally identifiable information (names, emails, payout details, addresses). This server is a **generic read-only GraphQL proxy** — the `graphql_query` tool can select any field the underlying token is allowed to read, so the guardrail against leaking PII is *prompt-level*, not enforced in code.

- Prefer running **locally** (the stdio transport below) so your data and token never leave your machine.
- Prefer **anonymous mode** (no token) when you only need public data — you then only ever see what the public API exposes.
- PII handling and safe field-selection guidance are prompt-level control points: the querying skill (`plugins/oc-platform-api/skills/querying-opencollective-graphql/`, shipped in the Claude plugin below), [AGENTS.md](AGENTS.md), and [docs/using-with-ai-safely.md](docs/using-with-ai-safely.md).

Tokens are never logged or persisted by this server.

## Claude Code plugin (easiest — bundles the MCP + skill + agent)

For Claude Code, install the plugin instead of wiring things up by hand. It ships the MCP server (stdio, via `uvx`), the querying skill, and an `opencollective-analyst` agent — all pinned to a released version:

```bash
/plugin marketplace add opensourceeurope/mcp-for-ocp-graphql
/plugin install oc-platform-api@ose-ai
```

Set `OC_PERSONAL_TOKEN` in your environment for authenticated access (optional — omit for anonymous public data). Prefer this over the manual stdio setup below if you use Claude Code.

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

### Hosted — Streamable HTTP + OAuth

**Prefer stdio (above) whenever your client supports it** — it's simpler and your data and token never leave your machine. Reach for the HTTP transport **only if your tool speaks MCP over HTTP and cannot launch a local stdio subprocess** — typically web/hosted assistants like claude.ai custom connectors or ChatGPT connectors. Desktop agents (Claude Code, Cursor, Windsurf, Zed, VS Code, LM Studio, Goose, Cherry Studio) all support stdio — use that.

The hosted server speaks MCP over Streamable HTTP and implements an OAuth 2.1 / PKCE **passthrough**: each user opens a browser form at `/oc-login` and pastes their own Open Collective personal token. That token becomes the OAuth access token and is forwarded to the OC API as the `Personal-Token` header on each query. The server mints no tokens of its own and stores no shared credentials.

#### Community instance

A shared instance is hosted for the community in the EU (Scaleway, `pl-waw`). Point an HTTP-only MCP client at it:

```bash
claude mcp add --transport http mcp-for-ocp-graphql \
  https://opensourceeuropeb9a9bb69-oc-graphql-mcp.functions.fnc.pl-waw.scw.cloud/mcp
```

On first use the client opens a browser for OAuth; paste your own Open Collective personal token. Each user authenticates independently — no shared token lives on the server.

> ⚠️ **Please don't overuse the community instance.** It's a small, cost-shared community deployment that scales to zero when idle — provided so people whose tools *can't* do stdio can still connect, not for heavy or automated load. If you query a lot, need guaranteed availability, or want to control the region, **run stdio locally** (above) or **self-host** (below) instead.

#### Self-host your own

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

1. **`search_docs(query, top_k=5)`** — keyword (BM25) search over a baked corpus of the Open Collective GraphQL guides plus a curated map of the top-level query fields (the entry points). Use this **first** to figure out which queries and fields you need. Each hit carries a `source_url` linking back to its source page.
2. **`schema_lookup(name)`** — exact definition of a GraphQL type or query field: its description, fields, and arguments (name, type, required, default). Substring matches return candidate names.
3. **`graphql_query(query, variables=None)`** — execute a read-only GraphQL query and return the JSON result. **Mutations and subscriptions are rejected**: every operation in the document is parsed and must be a `query`.

There are no per-operation typed tools — `graphql_query` is a single generic proxy that takes raw GraphQL, so field-selection and PII guidance live at the prompt level (the querying skill, AGENTS.md, and the safe-usage doc), not in code.

## Configuration

| Env var | Default | Used by | Description |
|---|---|---|---|
| `OC_PERSONAL_TOKEN` | _(unset → anonymous)_ | stdio | Open Collective personal token. Optional; not used by the HTTP server (which gets the token via OAuth). |
| `OC_GRAPHQL_ENDPOINT` | `https://api.opencollective.com/graphql/v2` | both | OC GraphQL API endpoint. |
| `PORT` | `3000` | HTTP | HTTP listen port. |
| `PUBLIC_URL` | `http://localhost:<PORT>` | HTTP | Publicly reachable server URL; OAuth 2.1 issuer. **Must be `https://` in production.** |

## Development

```bash
uv sync                # install runtime + dev deps from uv.lock
uv run pytest          # fast suite (offline; the e2e tests are excluded by default)
uv run pytest -m e2e   # opt-in end-to-end: live OC API + baked corpus (run after bumping OpenCrane)
uv run mcp-for-ocp-graphql   # run the stdio server locally from the source tree
```

### The docs corpus data

The wheel ships two artifacts under `mcp_for_ocp_graphql/data/`:

- **`schema.json`** — the introspected OC schema, used by `schema_lookup`.
- **`docs.json`** — the docs corpus (~40 KB of chunk text + provenance), searched with a pure-Python BM25 ranker in `search.py` for `search_docs`. No embedding model, no vector DB.

Both are **committed to the repo** (along with the corpus under `.opencrane/`) and regenerated by the [`corpus-refresh`](.github/workflows/corpus-refresh.yml) workflow:

```
schema_fetch → opencrane fetch → llms → chunk → docs_bake (chunks.json → data/docs.json)
```

OpenCrane (0.23.0) does fetch/llms/chunk; the bake step (`python -m mcp_for_ocp_graphql.docs_bake`) projects the chunks down to the slim `docs.json`. There is **no** embed/index step — doc search is lexical BM25, so nothing gets embedded and there is no vector database. (A dense-vector index was dropped: for ~74 tiny chunks it forced a multi-GB container and a cold-start model load for no real quality gain.)

The corpus is the six Open Collective GraphQL guides from [opencollective/graphql-docs-v2](https://github.com/opencollective/graphql-docs-v2) (fetched into `.opencrane/sources/`; © Open Collective, Inc., used under its upstream license) plus a **curated** schema slice — just the top-level query fields, generated by `python -m mcp_for_ocp_graphql.schema_ref --queries-only` from the introspected `schema.json`, not the full per-type dump (that duplicates `schema_lookup` and bloats the corpus). `corpus-refresh` runs weekly (and on demand) on Linux CI and opens a PR with the regenerated artifacts; image/wheel builds just consume the committed data, so they never re-introspect the schema at build time.

### Releases

Releases are automated with [release-please](https://github.com/googleapis/release-please) — no manual tagging or GitHub Release. Conventional-commit messages on `main` (`feat:` → minor, `fix:` → patch, `feat!`/`BREAKING CHANGE` → major) drive a rolling "release PR" that bumps `pyproject.toml` + the plugin's `plugin.json`, regenerates `CHANGELOG.md`, and syncs the plugin's `.mcp.json` pin. Merging that PR cuts the `vX.Y.Z` tag + GitHub Release and, in the same run, **publishes to PyPI** via trusted publishing. See [`.github/workflows/release.yml`](.github/workflows/release.yml) (its header lists the one-time maintainer setup: `RELEASE_TOKEN`, branch protection, and the PyPI trusted publisher).

## Stack & credits

- [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP)
- [graphql-core](https://github.com/graphql-python/graphql-core) — read-only query parsing/validation
- [httpx](https://www.python-httpx.org/) — GraphQL transport
- Pure-Python BM25 (`search.py`) — docs search, no model or vector DB
- OpenCrane CLI (`uvx opencrane`) — build-time docs corpus pipeline (`fetch` / `llms` / `chunk`; the slim `docs.json` is baked by this project's own `docs_bake.py`)
- [Open Collective GraphQL API v2](https://developers.opencollective.com/access)

MIT licensed.
