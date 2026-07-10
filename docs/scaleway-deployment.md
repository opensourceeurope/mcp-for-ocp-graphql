# Scaleway Deployment

Manual step-by-step deployment to [Scaleway Serverless Containers](https://www.scaleway.com/en/serverless-containers/).

**Prerequisites:** `scw` CLI configured, Docker running, default region `fr-par`.

---

## First deployment (one-time setup)

### 1. Create a Container Registry namespace

```bash
scw registry namespace create name=opencollective-mcp
```

Note the `endpoint` field in the output, e.g. `rg.fr-par.scw.cloud/opencollective-mcp`.

### 2. Authenticate Docker with the registry

```bash
scw registry login
```

### 3. Build and push the image

Replace `<registry-endpoint>` with the endpoint from step 1.

```bash
docker build -t mcp-for-ocp-graphql .
docker tag mcp-for-ocp-graphql <registry-endpoint>/opencollective-mcp:latest
docker push <registry-endpoint>/opencollective-mcp:latest
```

### 4. Create a Serverless Container namespace

```bash
scw container namespace create name=opencollective-mcp
```

Note the `id` field in the output.

### 5. Create the container

Replace `<namespace-id>` with the ID from step 4 and `<registry-endpoint>` from step 1.

> **Sizing:** the server is light — doc search is pure-Python BM25 over ~40 KB of JSON (no PyTorch, no embedding model, no vector DB), and the whole server peaks at ~70 MB RSS. **256 MB / 0.14 vCPU** gives ~3.5x headroom. Do **not** create it at Scaleway's 128 MB default — that leaves too little for Python + uvicorn under any concurrency and the container can crash-loop. (The [`build-and-push`](../.github/workflows/build-and-push.yml) deploy also floors these limits and fails the job if the container doesn't reach `ready`, so a redeploy self-corrects an undersized container.)

```bash
scw container container create \
  namespace-id=<namespace-id> \
  name=opencollective-mcp \
  registry-image=<registry-endpoint>/opencollective-mcp:latest \
  port=3000 \
  memory-limit=256 \
  cpu-limit=140 \
  min-scale=0 \
  max-scale=1 \
  environment-variables.PORT=3000 \
  deploy=true \
  --wait
```

> **scw version note:** these commands use `memory-limit` (MB) / `cpu-limit` (mvCPU), which is the arg naming through **scw ≤ 2.55.x**. scw **2.56+** renamed them to `memory-limit-bytes` (bytes) / `mvcpu-limit`. The CI deploy pins scw 2.55.0 for this reason; if you run a newer CLI by hand, translate accordingly (e.g. `memory-limit-bytes=268435456` for 256 MB).

Note the `domain-name` and `id` fields in the output.

### 6. Set PUBLIC_URL

OAuth requires the server to know its own public URL, which is only available after the container is created. Update it now.

```bash
scw container container update <container-id> \
  environment-variables.PUBLIC_URL=https://<domain-name> \
  deploy=true \
  --wait
```

### 7. Verify

```bash
curl https://<domain-name>/.well-known/oauth-authorization-server
```

Should return a JSON document with `issuer`, `authorization_endpoint`, and `token_endpoint`.

### 8. Register with Claude Code

```bash
claude mcp add --transport http mcp-for-ocp-graphql https://<domain-name>/mcp
```

Claude Code will open a browser for OAuth on first use. Enter your [Open Collective personal token](https://opencollective.com/dashboard/personal-tokens).

---

## Redeployment (every code change)

### 1. Build and push the updated image

```bash
docker build -t mcp-for-ocp-graphql .
docker tag mcp-for-ocp-graphql <registry-endpoint>/opencollective-mcp:latest
docker push <registry-endpoint>/opencollective-mcp:latest
```

### 2. Trigger a new deployment

```bash
scw container container deploy <container-id> --wait
```

---

## Useful commands

```bash
# List registries (to recover the endpoint)
scw registry namespace list

# List containers (to recover the container ID and domain)
scw container container list

# Get container details (URL, status, env vars)
scw container container get <container-id>
```
