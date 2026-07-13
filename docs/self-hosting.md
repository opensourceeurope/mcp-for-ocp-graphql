# Self-hosting the hosted (HTTP) server

The [README](../README.md) recommends the local **stdio** transport whenever your client supports it. Reach for the hosted **Streamable HTTP** transport only when your tool speaks MCP over HTTP and cannot launch a local stdio subprocess (typically web/hosted assistants like claude.ai custom connectors or ChatGPT connectors).

A shared [community instance](../README.md#hosted--streamable-http--oauth) exists, but it's a small, cost-shared deployment — if you query a lot, need guaranteed availability, or want to control the region, run your own instance as described below.

## How auth works

The hosted server implements an OAuth 2.1 / PKCE **passthrough**: each user opens a browser form at `/oc-login` and pastes their own Open Collective personal token. That token becomes the OAuth access token and is forwarded to the OC API as the `Personal-Token` header on each query. The server mints no tokens of its own and stores no shared credentials.

## Run with Docker

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

Runs on any EU container platform: Scaleway Serverless Containers (free tier), OVH, Hetzner. See **[scaleway-deployment.md](scaleway-deployment.md)** for a step-by-step Scaleway walkthrough.

## Configuration

| Env var | Default | Used by | Description |
|---|---|---|---|
| `OC_PERSONAL_TOKEN` | _(unset → anonymous)_ | stdio | Open Collective personal token. Optional; not used by the HTTP server (which gets the token via OAuth). |
| `OC_GRAPHQL_ENDPOINT` | `https://api.opencollective.com/graphql/v2` | both | OC GraphQL API endpoint. |
| `PORT` | `3000` | HTTP | HTTP listen port. |
| `PUBLIC_URL` | `http://localhost:<PORT>` | HTTP | Publicly reachable server URL; OAuth 2.1 issuer. **Must be `https://` in production.** |
