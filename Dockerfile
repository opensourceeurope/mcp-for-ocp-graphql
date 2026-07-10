# Hosted Streamable-HTTP server image for mcp-for-ocp-graphql.
#
# Committed-data approach: the docs/schema data
# (mcp_for_ocp_graphql/data/{schema.json, docs.json}) is COMMITTED to the repo and
# refreshed by .github/workflows/corpus-refresh.yml (which regenerates it with
# OpenCrane on Linux CI and commits it back). This Dockerfile just COPYs the project
# tree, so the image never hits the network for docs or the schema at build time.
# Doc search is pure-Python BM25 — no PyTorch/embedding model — so the image is slim.
FROM python:3.11-slim

# Pin uv via its official installer image (digest-pinned upstream) is overkill here;
# install a pinned uv version with pip instead so the toolchain is reproducible.
ENV UV_VERSION=0.8.19
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

WORKDIR /app

# Copy the whole project, including the CI-baked mcp_for_ocp_graphql/data/{schema.json,docs.json}.
COPY . .

# Install the project and its runtime deps (no dev group). Uses the committed
# uv.lock for a reproducible dependency set; --no-dev skips pytest etc.
RUN uv sync --no-dev --frozen

ENV PORT=3000
# PUBLIC_URL is read at runtime by app_http.build_http_app(); set it via the
# container platform (Scaleway) env. Defaults to http://localhost:$PORT if unset.
EXPOSE 3000

# Run the hosted HTTP entrypoint console script from the synced venv.
CMD ["uv", "run", "--no-dev", "--frozen", "mcp-for-ocp-graphql-http"]
