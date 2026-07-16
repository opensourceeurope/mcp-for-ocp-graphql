# MCP for OCP GraphQL API

An MCP server for the [Open Collective GraphQL API v2](https://api.opencollective.com/graphql/v2). It gives an AI assistant three tools to **learn the schema, search the docs, and run read-only queries** against Open Collective — without exposing any write operations.

## Contents

- [Using with AI safely](#using-with-ai-safely)
- [Prerequisite: install uv (one time)](#prerequisite-install-uv-one-time)
- [Install — Claude Code plugin (easiest)](#install--claude-code-plugin-easiest)
  - [Authorize for one session](#authorize-for-one-session)
  - [Authorize permanently](#authorize-permanently)
- [Two ways to run](#two-ways-to-run)
  - [Local — stdio (recommended)](#local--stdio-recommended)
  - [Hosted — Streamable HTTP + OAuth](#hosted--streamable-http--oauth)
- [The three tools](#the-three-tools)
- [Further reading](#further-reading)
- [Stack & credits](#stack--credits)

## Using with AI safely

Open Collective data includes personally identifiable information (names, emails, payout details, addresses). This server is a **generic read-only GraphQL proxy** — the `graphql_query` tool can select any field the underlying token is allowed to read, so the guardrail against leaking PII is *prompt-level*, not enforced in code.

- Prefer running **locally** (the stdio transport below) so your data and token never leave your machine.
- Prefer **anonymous mode** (no token) when you only need public data — you then only ever see what the public API exposes.

Tokens are never logged or persisted by this server. For the full PII posture and safe field-selection guidance, see **[docs/using-with-ai-safely.md](docs/using-with-ai-safely.md)**.

## Prerequisite: install uv (one time)

Everything here runs through a tool called **uv** (its `uvx` command is what actually launches the server). You install it once. **You do not need to install Python yourself** — uv quietly downloads the right Python for you the first time it runs.

Open a terminal, copy the line for your computer, and paste it in:

**macOS or Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows** (paste into PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> On a Mac that already has [Homebrew](https://brew.sh), `brew install uv` works too.

Then **close the terminal and open a new one** (so it can find the new command) and confirm it's there:

```bash
uv --version
```

If that prints a version number, you're set. Full instructions: [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/).

## Install — Claude Code plugin (easiest)

For Claude Code, install the plugin instead of wiring things up by hand. It ships the MCP server (stdio, via `uvx`), the querying skill, and an `opencollective-analyst` agent — all pinned to a released version. Plugins install at **user scope** (globally, across all your projects), which is the recommended setup:

```bash
/plugin marketplace add opensourceeurope/mcp-for-ocp-graphql
/plugin install oc-platform-api@ose-ai
/reload-plugins
```

`/reload-plugins` activates it right away (loading the skills, agent, and MCP server) — no need to quit; if in doubt you can also just restart Claude Code.

**By default it runs anonymously** — public Open Collective data only, no token. That's the safest mode and enough for most public queries.

To read non-public data you supply your own personal token, created in your Dashboard under **For developers** (`https://opencollective.com/dashboard/<your-slug>/for-developers`). The plugin's bundled config has no slot to store one, so the token reaches the server through the environment. Two options:

### Authorize for one session

Export the token, then launch Claude Code from that same shell (the `uvx` subprocess inherits it):

```bash
export OC_PERSONAL_TOKEN=oc_xxx && claude
```

### Authorize permanently

Register your own user-scoped server with the token baked in. It's stored in your personal `~/.claude.json` (never committed to any repo). The `remove` makes re-running safe:

```bash
claude mcp remove -s user oc-platform-api 2>/dev/null
claude mcp add -s user -e OC_PERSONAL_TOKEN=oc_xxx \
  -t stdio oc-platform-api -- uvx mcp-for-ocp-graphql
```

Restart Claude Code afterwards to load it (this is a standalone server, so `/reload-plugins` won't pick it up). This standalone server exposes the same three tools, authenticated — it runs *alongside* the plugin's anonymous one, so you'll see the tools twice (redundant, not broken). If that bothers you, skip the `mcp add` and instead put `export OC_PERSONAL_TOKEN=oc_xxx` in your shell profile (`~/.zshrc`, `~/.bashrc`): the plugin's own server then starts authenticated every session, with no second server.

## Two ways to run

### Local — stdio (recommended)

Runs entirely on your machine over the MCP stdio transport. A token is **optional**: with no token the server runs anonymously against public data; with a token it can read whatever that token is authorized for. Published to [PyPI](https://pypi.org/project/mcp-for-ocp-graphql/) and run with `uvx`.

```bash
# anonymous (public data only)
uvx mcp-for-ocp-graphql

# authenticated — create a token under Dashboard → For developers
# (https://opencollective.com/dashboard/<your-slug>/for-developers)
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

**Prefer stdio (above) whenever your client supports it** — it's simpler and your data and token never leave your machine. Reach for the HTTP transport **only if your tool speaks MCP over HTTP and cannot launch a local stdio subprocess** — typically web/hosted assistants like claude.ai custom connectors or ChatGPT connectors. Desktop agents (Claude Code, Cursor, Windsurf, Zed, VS Code) all support stdio — use that.

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

## Stack & credits

- [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP)
- [graphql-core](https://github.com/graphql-python/graphql-core) — read-only query parsing/validation
- [httpx](https://www.python-httpx.org/) — GraphQL transport
- Pure-Python BM25 (`search.py`) — docs search, no model or vector DB
- [OpenCrane CLI](https://github.com/derberg/OpenCrane) (`uvx opencrane`) — build-time docs corpus pipeline (`fetch` / `llms` / `chunk`; the slim `docs.json` is baked by this project's own `docs_bake.py`)
- [Open Collective GraphQL API v2](https://developers.opencollective.com/access)

MIT licensed.
