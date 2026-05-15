MCP server for the [Open Collective GraphQL API](https://api.opencollective.com/graphql/v2).

Introspects the full OC schema on startup and exposes every query operation as an MCP tool. Mutations are excluded.

Implements OAuth 2.1 with PKCE. Each user authenticates with their own OC personal token through a browser form — no shared server-side token is needed.

## Requirements

- Node.js 18+
- Docker (for container hosting)

## Hosted usage (Docker)

```bash
docker build -t opencollective-mcp .

# default port 3000
docker run -d --name oc-mcp -p 3000:3000 opencollective-mcp

# custom port (e.g. 8080)
docker run -d --name oc-mcp -p 8080:8080 -e PORT=8080 opencollective-mcp
```

Set `PUBLIC_URL` to the publicly reachable URL of your server — used as the OAuth issuer and in auth discovery metadata:

```bash
docker run -d --name oc-mcp -p 8080:8080 \
  -e PORT=8080 \
  -e PUBLIC_URL=https://your-host \
  opencollective-mcp
```

Register with Claude Code:

```bash
claude mcp add --transport http opencollective https://your-host/mcp
```

Claude Code will prompt you to authenticate on first use. A browser opens showing a form to enter your OC personal token. Get one at `https://opencollective.com/dashboard/personal-tokens`. Each user authenticates independently — no shared token is needed on the server.

Works on any EU container platform: Scaleway Serverless Containers (free tier), OVH, Hetzner.

> **Production note:** `PUBLIC_URL` must use `https://` in production. OAuth 2.1 requires HTTPS for all non-localhost endpoints. Redirect URIs over plain HTTP will be rejected by the auth layer.

### Day-to-day commands

```bash
# rebuild image and restart container
docker build --no-cache -t opencollective-mcp . && (docker rm -f oc-mcp 2>/dev/null || true) && docker run -d --name oc-mcp -p 8080:8080 -e PORT=8080 opencollective-mcp

# check the container is running
docker ps --filter name=oc-mcp

# tail logs
docker logs oc-mcp --tail 50 --follow

# stop / restart
docker stop oc-mcp
docker start oc-mcp
```

## Configuration

| Env var | Default | Description |
|---|---|---|
| `OC_GRAPHQL_ENDPOINT` | `https://api.opencollective.com/graphql/v2` | OC API endpoint |
| `PORT` | `3000` | HTTP port |
| `PUBLIC_URL` | `http://localhost:<PORT>` | Publicly reachable server URL; used as OAuth 2.1 issuer. **Must be `https://` in production.** |

## Development

```bash
npm test      # run unit tests
node index.js # run locally
```

Start the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) against a locally running server:

```bash
npx @modelcontextprotocol/inspector@0.21.2 --transport http --server-url http://localhost:8080/mcp
```

## Stack

- [Model Context Protocol SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Open Collective GraphQL API v2](https://developers.opencollective.com/access)
