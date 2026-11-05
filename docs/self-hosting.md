# Self-hosting the HTTP server

The [README](../README.md) recommends the local stdio transport whenever your client supports it. Use the Streamable HTTP transport only when your MCP client cannot start a local process, such as claude.ai custom connectors or ChatGPT connectors.

Open Source Europe does not run a public instance of this server, and the project does not publish a container image. To use the HTTP transport, build the image from this repository and run your own instance as this page describes.

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

The image runs on any platform that runs containers. Pick a region that fits your data protection needs, for example an EU region for GDPR.

## Configuration

| Env var | Default | Used by | Description |
|---|---|---|---|
| `OC_PERSONAL_TOKEN` | _(unset → anonymous)_ | stdio | Open Collective personal token. Optional; not used by the HTTP server (which gets the token via OAuth). |
| `OC_GRAPHQL_ENDPOINT` | `https://api.opencollective.com/graphql/v2` | both | OC GraphQL API endpoint. |
| `PORT` | `3000` | HTTP | HTTP listen port. |
| `PUBLIC_URL` | `http://localhost:<PORT>` | HTTP | Publicly reachable server URL; OAuth 2.1 issuer. **Must be `https://` in production.** |
