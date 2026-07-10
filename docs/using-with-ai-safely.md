# Using this MCP with AI safely

This MCP exposes the full Open Collective GraphQL API. Some fields contain personal data (emails, phone numbers, addresses, payout details, billing info). This guide explains how to use the MCP with an AI assistant with a clear-eyed view of where that data ends up, so you can decide what you're comfortable with.

## The one rule that matters

**Whoever runs the model sees everything the model sees.** For a hosted model (Claude, ChatGPT, Gemini) that's the provider — Anthropic, OpenAI, Google. For a local model (Ollama, LM Studio, llama.cpp) that's just you, on your machine. Either way, anything the model "reads" — tool results, file contents, pasted text — has crossed into that environment. The MCP server itself just relays GraphQL responses; it does not, and cannot, redact what you ask the model to look at after the fact.

That means safety is decided **before** the call: which kind of model you're running, and what you ask it to retrieve.

## Two safe modes

### Mode A — Hosted AI (Claude, ChatGPT, Gemini, etc.)

**Default: do not ask the AI to retrieve PII fields.** Once a personal email appears in a tool result, it has already been sent to the AI provider's servers — the default cannot be honored after retrieval.

**You can override the default for a specific request.** If you genuinely need the AI to work with PII, ask for it explicitly knowing that (a) the data will reach the model provider and (b) anywhere the AI then writes it — files, commits, messages it sends on your behalf — is a further disclosure. With that awareness, it's your data and your call.

Safe to ask the AI for (no awareness step needed):

- Public collective metadata (names, slugs, descriptions, tags, logos, URLs)
- Aggregates: expense counts, transaction totals, balances, member counts
- Time-series analysis: expenses per month, trends, top contributors *by count*
- Host-level rollups, fund flow analysis, category breakdowns

Counts as personal data — think before asking:

- `email` or `emails` on any account
- `phoneNumber`, `address`, `legalName` on individual accounts
- Payout method details, billing details, payment provider identifiers
- Anything inside `payoutMethod`, `paymentMethod`, or `location` on an Individual

### Mode B — Local AI (Ollama, LM Studio, llama.cpp)

Run the model on your own hardware. Data stays on your machine — no provider sees the tool results or the conversation. PII handling is much less restrictive here: ask the model whatever you need. The remaining things to watch for are downstream:

- Don't paste transcripts containing PII into anything cloud-hosted later (a hosted AI, a pastebin, a shared doc).
- Files the local model writes (CSVs, reports, commits) are still PII on disk — handle them under the same care you'd give any export of personal data (encrypted disk, no public repos, GDPR retention rules).
- If you sync your home directory to a cloud backup, those files leave your machine.

For a copy-paste setup, pick the one that matches you:

- **Desktop app, no terminal** — [local-agent-with-ui.md](local-agent-with-ui.md) (LM Studio).
- **Command-line / developer** — [local-agent-with-ollama.md](local-agent-with-ollama.md) (Ollama + Goose).

Both keep everything on your machine and take ~15 minutes end-to-end including the model download.

## Pinning the rule so the AI applies it consistently

Telling the model "be careful with PII" inside a chat works *sometimes*. Pinning it as a **project instruction** works reliably — the AI will warn you before fetching personal data and then defer to your call. The exact mechanism depends on your client:

| Client | Where to put the instruction |
|---|---|
| Claude Code | `AGENTS.md` or `CLAUDE.md` at repo root |
| Claude.ai (Projects) | Project instructions panel |
| ChatGPT (Custom GPT or Project) | Instructions field |
| Cursor / Windsurf | `.cursorrules` / project rules |

Copy-paste this instruction (works for both hosted and local models):

```markdown
## Handling Personal Data

The Open Collective MCP can return personal data (emails, phone numbers,
addresses, payout/billing details on Individual accounts). Pulling any
PII field into a tool result puts it in the model's processing context —
for a hosted model that means transmission to the provider's servers,
for a local model it stays on my machine. Writing it to a file, commit,
or message is a further disclosure either way.

- By default, do not select PII fields in any MCP/GraphQL query:
  `email`, `emails`, `phoneNumber`, `address`, `legalName`, anything
  inside `payoutMethod`, `paymentMethod`, or `location` on an Individual.
- If I ask for PII (or you'd recommend fetching it): tell me plainly
  what will happen — including whether you're running under a hosted
  model (data reaches the provider) or a local one (stays on my
  machine). If you don't know, say so. Once I confirm with that
  knowledge, do what I asked.
- Preferred alternative when possible: give me the command to run in
  my own terminal, so the PII stays local regardless of which model
  I'm using.
```

The agent-facing version of this rule is in [`AGENTS.md`](../AGENTS.md) (used automatically by Claude Code) and codified for query work in the [`querying-opencollective-graphql` skill](../plugins/opencollective-graphql/skills/querying-opencollective-graphql/SKILL.md).

## When you genuinely need the PII

Don't ask the AI. Run it yourself in your terminal — the response stays on your machine:

```bash
# Run this in your OWN terminal.
# Do NOT use Claude Code's `!` prefix — that routes the output back through the model.
export OC_TOKEN='<your personal token from https://opencollective.com/dashboard/personal-tokens>'

curl -s https://api.opencollective.com/graphql/v2 \
  -H 'Content-Type: application/json' \
  -H "Personal-Token: $OC_TOKEN" \
  -d '{"query":"query($s:String){account(slug:$s){members(role:ADMIN){nodes{account{name slug emails}}}}}","variables":{"s":"COLLECTIVE_SLUG"}}'
```

Replace `COLLECTIVE_SLUG`. The emails land in your terminal. They never enter any AI context.

If you need to share the result with a collaborator: do it through a channel you already trust for PII (e.g. encrypted email, password manager share) — not by pasting into a chat with an AI.

## What about the MCP server itself?

The MCP server in this repo:

- Runs in one of two modes. **Hosted (HTTP + OAuth 2.1 + PKCE):** a shared server with no shared credentials — each user authenticates with their own Open Collective personal token. **Local (stdio):** you run the server yourself with your token in the `OC_PERSONAL_TOKEN` env var; it never touches a third-party host at all.
- Does not persist tokens or query results. The token is held only in memory — in hosted mode for the duration of each request, in local stdio mode for the life of the running process — and is never written to disk or logged by the server. In local mode, the one on-disk copy is whatever you place in your own MCP client config.
- Does not log tokens, headers, or request bodies (see [`AGENTS.md`](../AGENTS.md) › "Never log tokens").
- Is read-only — the `graphql_query` tool parses every operation in the document and rejects anything that isn't a `query` (mutations and subscriptions error before any network call).

For maximum control, **run the server yourself** rather than using one operated by someone else. The most local option is **stdio mode on your own machine** (`uvx mcp-for-ocp-graphql`) — then the only third party that sees your queries is Open Collective, which already holds the data. If you need a shared HTTP server for a team, host your own instance (Scaleway, OVH, Hetzner — see [`docs/scaleway-deployment.md`](scaleway-deployment.md)). With your own instance:

- You control the host region (keep it in the EU for GDPR purposes).
- You control the logs.
- The only third party that sees your queries is Open Collective itself, which already holds the data.

## Quick checklist before any AI session

1. Hosted or local model? → Hosted = anything PII reaches the provider. Local = stays on your machine, but disk artifacts (files, commits, backups) still count as exports.
2. Is the project instruction with the PII rule pinned in the client?
3. Do you need a field that contains personal data? → Prefer the curl recipe (Mode-agnostic, stays local). If you do ask the AI, do it deliberately and knowing where the data ends up.
4. About to paste a transcript or tool result somewhere? → Skim it for emails/phone/address first, especially if the next destination is cloud-hosted.

## Further reading

- [Open Collective personal tokens](https://opencollective.com/dashboard/personal-tokens)
- [Open Collective GraphQL v2 docs](https://developers.opencollective.com/access)
- [GDPR Art. 4(1) — definition of personal data](https://gdpr-info.eu/art-4-gdpr/)
