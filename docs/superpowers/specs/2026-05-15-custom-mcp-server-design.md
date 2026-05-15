# Custom MCP Server for Open Collective GraphQL API

**Date:** 2026-05-15
**Status:** Approved

## Goal

Replace the reShapr Docker Compose stack (control plane + gateway + Postgres) with a lightweight custom Node.js MCP server. The server introspects the Open Collective GraphQL API on startup and exposes all query operations as MCP tools.

## What Gets Removed

- `schemas/` directory and `schemas/opencollective.graphql`
- `scripts/refresh-schema.sh`
- `scripts/print-mcp-config.sh`
- All reShapr-related env vars from `.env.example`

## File Structure

```
index.js              ← entry point: wires transport, starts server
src/schema.js         ← introspects OC API on startup, returns parsed operations
src/tools.js          ← maps GraphQL operations → MCP tool definitions + executors
Dockerfile            ← minimal image for container hosting
.env.example          ← OC_PERSONAL_TOKEN, PORT
package.json
README.md             ← rewritten for new setup
```

## Architecture

### Startup Flow

1. Fetch GraphQL introspection from `https://api.opencollective.com/graphql/v2`
2. Parse the `Query` type — collect all operations with their arguments and docstrings
3. Generate one MCP tool per operation: name = operation name, description = docstring, inputSchema = arguments mapped to JSON Schema
4. Start transport based on `--stdio` flag: stdio (local) or HTTP on `PORT` (hosted)

### Auth

`OC_PERSONAL_TOKEN` env var controls auth mode:

- **Not set:** anonymous requests — public OC rate limits (10 req/min), public data only
- **Set:** adds `Personal-Token: <value>` header to every OC GraphQL request — 100 req/min, account-scoped data

A single server instance handles one auth mode. Run two instances (different ports) if both modes are needed.

### Transport

| Flag / env | Transport | Use case |
|---|---|---|
| `--stdio` arg | stdio | Local Claude Code via `claude mcp add --transport stdio` |
| default (no flag) | HTTP on `PORT` (default 3000) | Hosted — Docker container, Claude Code via `claude mcp add --transport http` |

### Tool Generation

Each GraphQL `Query` operation becomes one MCP tool:

- **name:** operation name (camelCase, e.g. `currencyExchangeRate`)
- **description:** operation docstring from the schema
- **inputSchema:** operation arguments mapped to JSON Schema types (`String` → `string`, `Int` → `number`, `Boolean` → `boolean`, etc.); required arguments = required fields
- **execution:** sends `{ query: "{ operationName(args) { ...allFields } }", variables: { ... } }` to OC API, returns result

### Error Handling

- If introspection fails on startup → log error and exit (no point running with no tools)
- If a tool call fails → return MCP error response with the GraphQL error message

## Dependencies

- `@modelcontextprotocol/sdk` — MCP server + transports
- Native `fetch` (Node.js 18+) — GraphQL HTTP requests
- No other runtime dependencies

## Local Usage

```bash
npm install
# anonymous
node index.js --stdio

# with personal token
OC_PERSONAL_TOKEN=xxx node index.js --stdio

# register with Claude Code
claude mcp add --transport stdio opencollective -- node /abs/path/to/index.js
# with token (set in shell env or prefix the command):
claude mcp add --transport stdio opencollective-pt -- env OC_PERSONAL_TOKEN=xxx node /abs/path/to/index.js
```

## Hosted Usage (Docker)

```bash
docker build -t opencollective-mcp .
docker run -p 3000:3000 -e OC_PERSONAL_TOKEN=xxx opencollective-mcp

# register with Claude Code
claude mcp add --transport http opencollective http://your-host:3000/mcp
```

Target platforms: Scaleway Serverless Containers (EU, free tier) or OVH (user has non-profit discounts). Same Docker image works on both.

## Constraints

- Node.js 18+ required (native fetch)
- Mutations excluded — only `Query` operations are exposed
- No caching of introspection result across restarts (fetch on each startup is fast enough)
