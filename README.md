# MCP for OCP GraphQL API

An MCP server for the [Open Collective GraphQL API v2](https://api.opencollective.com/graphql/v2). It gives an AI assistant three tools to **learn the schema, search the docs, and run read-only queries** against Open Collective — without exposing any write operations.

## Using with AI safely

Open Collective data includes personally identifiable information (names, emails, payout details, addresses). This server is a **generic read-only GraphQL proxy** — the `graphql_query` tool can select any field the underlying token is allowed to read, so the guardrail against leaking PII is *prompt-level*, not enforced in code.

- Prefer running **locally** (the stdio transport below) so your data and token never leave your machine.
- Prefer **anonymous mode** (no token) when you only need public data — you then only ever see what the public API exposes.

Tokens are never logged or persisted by this server. For the full PII posture and safe field-selection guidance, see **[docs/using-with-ai-safely.md](docs/using-with-ai-safely.md)**.

## Install — Claude Code plugin (easiest)

For Claude Code, install the plugin instead of wiring things up by hand. It ships the MCP server (stdio, via `uvx`), the querying skill, and an `opencollective-analyst` agent — all pinned to a released version:

```bash
/plugin marketplace add opensourceeurope/mcp-for-ocp-graphql
/plugin install oc-platform-api@ose-ai
```

Set `OC_PERSONAL_TOKEN` in your environment for authenticated access (optional — omit for anonymous public data). Prefer this over the manual stdio setup below if you use Claude Code.

## Two ways to run

### Local — stdio (recommended)

Runs entirely on your machine over the MCP stdio transport. A token is **optional**: with no token the server runs anonymously against public data; with a token it can read whatever that token is authorized for. Published to [PyPI](https://pypi.org/project/mcp-for-ocp-graphql/) and run with `uvx`.

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

`OC_PERSONAL_TOKEN` is delivered to the server as a process environment variable — either via the config's `env` block above or exported in your shell before launch (there is no CLI flag for it). Omit it to run anonymously.

### Hosted — Streamable HTTP + OAuth

**Prefer stdio (above) whenever your client supports it** — it's simpler and your data and token never leave your machine. Reach for the HTTP transport **only if your tool speaks MCP over HTTP and cannot launch a local stdio subprocess** — typically web/hosted assistants like claude.ai custom connectors or ChatGPT connectors. Desktop agents (Claude Code, Cursor, Windsurf, Zed, VS Code, LM Studio, Goose, Cherry Studio) all support stdio — use that.

Each user authenticates with their own Open Collective personal token via an OAuth 2.1 / PKCE passthrough (a browser form at `/oc-login`); the server mints no tokens of its own and stores no shared credentials.

A shared **community instance** is hosted for the community in the EU (Scaleway, `pl-waw`). Point an HTTP-only MCP client at it:

```bash
claude mcp add --transport http mcp-for-ocp-graphql \
  https://opensourceeuropeb9a9bb69-oc-graphql-mcp.functions.fnc.pl-waw.scw.cloud/mcp
```

On first use the client opens a browser for OAuth; paste your own Open Collective personal token. Each user authenticates independently — no shared token lives on the server.

> ⚠️ **Please don't overuse the community instance.** It's a small, cost-shared community deployment that scales to zero when idle — provided so people whose tools *can't* do stdio can still connect, not for heavy or automated load. If you query a lot, need guaranteed availability, or want to control the region, **run stdio locally** (above) or **[self-host your own](docs/self-hosting.md)** instead.

To run your own HTTP instance, see **[docs/self-hosting.md](docs/self-hosting.md)** (Docker + configuration reference).

## The three tools

The intended flow is **learn, then execute**:

1. **`search_docs(query, top_k=5)`** — keyword (BM25) search over a baked corpus of the Open Collective GraphQL guides plus a curated map of the top-level query fields (the entry points). Use this **first** to figure out which queries and fields you need. Each hit carries a `source_url` linking back to its source — deep-linked to the exact section (`#anchor`) where the guide chunk has one.
2. **`schema_lookup(name)`** — exact definition of a GraphQL type or query field: its description, fields, and arguments (name, type, required, default). Substring matches return candidate names.
3. **`graphql_query(query, variables=None)`** — execute a read-only GraphQL query and return the JSON result. **Mutations and subscriptions are rejected**: every operation in the document is parsed and must be a `query`.

## Further reading

- **[Using with AI safely](docs/using-with-ai-safely.md)** — the PII posture and safe field-selection guidance.
- **[Self-hosting](docs/self-hosting.md)** — run your own hosted HTTP server via Docker, plus the full configuration reference.
- **[Scaleway deployment](docs/scaleway-deployment.md)** — step-by-step walkthrough for the hosted HTTP server on Scaleway.
- **[Development](docs/development.md)** — local dev setup, the docs-corpus pipeline, and the release process.
- Local stdio setups end to end: **[with Ollama](docs/local-agent-with-ollama.md)** · **[with a UI](docs/local-agent-with-ui.md)**.

## Stack & credits

- [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP)
- [graphql-core](https://github.com/graphql-python/graphql-core) — read-only query parsing/validation
- [httpx](https://www.python-httpx.org/) — GraphQL transport
- Pure-Python BM25 (`search.py`) — docs search, no model or vector DB
- OpenCrane CLI (`uvx opencrane`) — build-time docs corpus pipeline (`fetch` / `llms` / `chunk`; the slim `docs.json` is baked by this project's own `docs_bake.py`)
- [Open Collective GraphQL API v2](https://developers.opencollective.com/access)

MIT licensed.
