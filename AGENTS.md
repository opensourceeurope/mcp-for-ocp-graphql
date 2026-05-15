# opencollective-mcp — Agent Instructions

MCP server that introspects the Open Collective GraphQL API at startup and exposes every query operation as an MCP tool. HTTP-only, OAuth 2.1 with PKCE. Licensed under MIT.

## Authorship Rules

- **NEVER add `Co-Authored-By:` with yourself as a co-author of any commit.** Agents are assistants and tools — they are not authors. Only humans can be authors of commits.
- AI assistance disclosure belongs in the pull request description using the exact format below — not in commit authorship metadata:
  ```
  Generated-by: <Agent Name and Version> following [AI Policy](https://github.com/opensourceeurope/.github/blob/main/AI-POLICY.md)
  ```

## Commit Conventions

- Use conventional commits: `feat:`, `fix:`, `docs:`, `ci:`, `chore:`
- This project is MIT-licensed — do not introduce incompatibly licensed material

## Running Tests

```bash
npm test
```

Tests use the Node.js built-in test runner (`node --test`). No Jest, no Vitest. Follow TDD: write the failing test first, watch it fail, then implement.

## Architecture

**Startup**: `fetchSchema(endpoint)` introspects the OC GraphQL API anonymously (no token needed). `buildTools(schema, endpoint, tokenGetter)` maps each query field to an MCP tool.

**Per request**: The bearer token from the OAuth handshake is threaded through `AsyncLocalStorage` into the tool handlers, which forward it as a `Personal-Token` header on every GraphQL call. OC validates the token naturally on each query — there is no server-side token cache.

**Auth flow**: `createOAuthProvider` in `src/auth.js` implements the full OAuth 2.1 authorization server. Authorization codes live in memory for 30 seconds and are deleted after a single exchange. `verifyAccessToken` is intentionally a presence-only check — it does not call the OC API. OC rejects bad tokens on first use.

## Key Decisions — Do Not Quietly Undo

- **No stdio mode, no `OC_PERSONAL_TOKEN`.** HTTP + OAuth only. Every user authenticates with their own token.
- **`verifyAccessToken` does not call OC.** It checks that a token string is present. Double-validation on every request was explicitly removed as unnecessary — OC does it when the tool actually runs.
- **Read-only.** Only query operations are exposed. Mutations are excluded at schema introspection time and must stay excluded.
- **`buildSelection` caps depth at 3 and skips UNION types.** This keeps generated GraphQL queries from becoming unboundedly large. Do not raise the depth limit without understanding the query size implications.
- **Hardcoded descriptions in `src/tools.js`.** The `DESCRIPTIONS` map provides meaningful per-operation descriptions that the OC schema itself lacks. If new query operations appear, add entries there rather than falling back to the camelCase→words conversion.
- **XSS escaping in `src/auth.js`.** The `escape()` function must be applied to every user-controlled value rendered into HTML. The auth form is a security boundary — treat it accordingly.
- **Never log tokens.** The bearer token / `Personal-Token` value must never appear in logs, error messages, or stack traces. When adding debug output, log operation names and status codes — not headers or request bodies that may contain the token.
