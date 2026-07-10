#!/usr/bin/env bash
# Pin the plugin's MCP package spec to the release version.
#
# release-please owns the version (.release-please-manifest.json, key ".") and bumps
# pyproject.toml + the plugin.json version (via extra-files) itself. But it can't
# cleanly rewrite `mcp-for-ocp-graphql==X.Y.Z` inside .mcp.json — its json updater
# writes a bare value and clobbers the `pkg==` prefix. So this one bit is done here,
# run on the release-PR branch before the PR merges.
#
# Usage: ./scripts/sync-plugin-version.sh          (reads the version from the manifest)
#        ./scripts/sync-plugin-version.sh 0.2.0     (override — handy for manual runs/tests)
# Idempotent: re-running with the same version is a no-op.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  VERSION="$(python3 -c 'import json; print(json.load(open(".release-please-manifest.json"))["."])')"
fi
printf '%s' "$VERSION" | grep -qE '^[0-9A-Za-z.+_-]+$' || {
  echo "ERROR: refusing to use invalid version '$VERSION'" >&2
  exit 1
}

FILE="plugins/oc-platform-api/.mcp.json"
# The only `mcp-for-ocp-graphql` occurrence in .mcp.json is the uvx arg pin; rewrite it
# (with or without an existing ==spec) to ==$VERSION.
VERSION="$VERSION" perl -i -pe 's/(mcp-for-ocp-graphql)(==[0-9A-Za-z.+_-]+)?/"$1==$ENV{VERSION}"/ge' "$FILE"
echo "pinned $FILE -> mcp-for-ocp-graphql==$VERSION"
