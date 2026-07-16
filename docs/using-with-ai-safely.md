# Using this MCP with AI safely

This MCP exposes the full Open Collective GraphQL API. Some fields contain personal data (emails, phone numbers, addresses, payout details, billing info). This guide explains where that data ends up when you use the MCP with an AI assistant, so you can decide what you're comfortable with.

The recommended setup is **Claude Code with a regular Claude model**, connected via the [plugin](../README.md#install--claude-code-plugin-easiest). Any MCP client works, but the rules below are written for that hosted case — it's the one where getting PII wrong actually leaks something.

## The one rule that matters

**Whoever runs the model sees everything the model sees.** With a hosted assistant (Claude Code, ChatGPT, Gemini) that's the provider — Anthropic, OpenAI, Google. Anything the model *reads* — tool results, file contents, pasted text — has crossed onto the provider's servers. The MCP server itself just relays GraphQL responses; it does not, and cannot, redact what you ask the model to look at after the fact.

So safety is decided **before** the call, by what you ask the AI to retrieve.

## Default: keep personal data out of the model

**Don't ask the AI to select PII fields.** Once a personal email lands in a tool result, it has already been sent to the provider — you can't take it back.

Safe to ask the AI for (no special care needed):

- Public collective metadata (names, slugs, descriptions, tags, logos, URLs)
- Aggregates: expense counts, transaction totals, balances, member counts
- Time-series analysis: expenses per month, trends, top contributors *by count*
- Host-level rollups, fund-flow analysis, category breakdowns

Counts as personal data — don't put it in the model:

- `email` or `emails` on any account
- `phoneNumber`, `address`, `legalName` on individual accounts
- Payout method details, billing details, payment provider identifiers
- Anything inside `payoutMethod`, `paymentMethod`, or `location` on an Individual

## When you genuinely need the PII — delegate to a script

Don't have the AI fetch it. Have the AI **write a script that you run yourself**:

1. The agent authors the query/script from the schema — **no PII in that step**.
2. **You** run it in your own terminal, passing your own token.
3. The results are written to a local file — Markdown, CSV, or PDF — that the **AI never reads**.

The personal data flows API → your disk, entirely outside the model. In Claude Code with the [plugin](../README.md#install--claude-code-plugin-easiest) this is automated — the `exporting-personal-data-locally` skill generates a ready-to-run `uv` script (CSV, Markdown, or PDF) and never fetches the data itself. With any other client, ask for exactly that, for example:

> Write me a standalone script that fetches the ADMIN names and emails for collective `X` and writes them to `admins.csv`. I'll run it myself with my own token — don't run it, and don't fetch the data yourself.

Then run it and open the file. A minimal hand-written version, if you'd rather not have the agent generate one:

```bash
# Run this in your OWN terminal (needs curl + jq).
# Do NOT use Claude Code's `!` prefix — that routes the output back through the model.
export OC_TOKEN='<your token — Dashboard → For developers: https://opencollective.com/dashboard/<your-slug>/for-developers>'

# ADMIN members of the AsyncAPI Initiative, printed as a name / slug / emails table.
# `emails` lives on Individual, so it needs an inline fragment (... on Individual).
# -A: Cloudflare in front of the API 403s default curl/python user agents (error 1010).
curl -s https://api.opencollective.com/graphql/v2 \
  -A 'Mozilla/5.0 (compatible; oc-local-export/1.0)' \
  -H 'Content-Type: application/json' \
  -H "Personal-Token: $OC_TOKEN" \
  -d '{"query":"query($s:String){account(slug:$s){members(role:ADMIN){nodes{account{name slug ... on Individual{emails}}}}}}","variables":{"s":"asyncapi"}}' \
| jq -r '["NAME","SLUG","EMAILS"], (.data.account.members.nodes[].account | [.name, .slug, (.emails // [] | join(", "))]) | @tsv' \
| column -t -s $'\t'
```

Output is a clean table, e.g.:

```
NAME                   SLUG               EMAILS
Lukasz Gornicki        lukasz-gornicki3   lukasz@example.org
V. Thulisile Sibanda   thulieblack        thuli@example.org
Hugo Guerrero          hugo-guerrero      hugo@example.org
```

Swap `asyncapi` for your own collective's slug. The table prints in your terminal — the emails never enter any AI context. (Prefer the raw JSON on disk? Drop the `| jq … | column …` pipes and append `> admins.json` instead.) If the agent generated this for you, skim it before running: it should only *query and print/write*, and read your token from your own environment (never hard-code it).

If you need to share the result: use a channel you already trust for PII (encrypted email, a password-manager share) — not by pasting it into a chat with an AI.

## Pinning the rule so the AI applies it consistently

Telling the model "be careful with PII" mid-chat works *sometimes*. Pinning it as a **project instruction** works reliably — the AI will refuse to pull personal data into its context and offer you a script instead. Where the instruction goes depends on your client:

| Client | Where to put the instruction |
|---|---|
| Claude Code | `AGENTS.md` or `CLAUDE.md` at repo root |
| Claude.ai (Projects) | Project instructions panel |
| ChatGPT (Custom GPT or Project) | Instructions field |
| Cursor / Windsurf | `.cursorrules` / project rules |

Copy-paste this instruction:

```markdown
## Handling Personal Data

The Open Collective MCP can return personal data (emails, phone numbers,
addresses, payout/billing details on Individual accounts). Pulling any
PII field into a tool result puts it in the model's context — for a
hosted model that means transmission to the provider's servers. Writing
it to a file, commit, or message is a further disclosure.

- By default, do not select PII fields in any MCP/GraphQL query:
  `email`, `emails`, `phoneNumber`, `address`, `legalName`, anything
  inside `payoutMethod`, `paymentMethod`, or `location` on an Individual.
- If I ask for PII: don't fetch it yourself. Write me a standalone
  script (Python or curl) that I run in my own terminal with my own
  token, writing the results to a local file (Markdown, CSV, or PDF).
  The data then never enters your context. Don't run it yourself.
- Only if I explicitly insist you fetch it directly: tell me plainly
  that the data will reach the model provider, and proceed only after
  I confirm with that knowledge.
```

The agent-facing version of this rule ships in the **plugin** — the [`querying-opencollective-graphql` skill](../plugins/oc-platform-api/skills/querying-opencollective-graphql/SKILL.md) and the [`opencollective-analyst` agent](../plugins/oc-platform-api/agents/opencollective-analyst.md) — which Claude Code applies automatically. It lives with the plugin, not in `AGENTS.md`, because it governs *querying the MCP*, not *developing this repo*.

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

1. Is the project instruction with the PII rule pinned in your client?
2. Does the task need a field that contains personal data? → Don't ask the AI to fetch it. Have the agent generate a script you run yourself (results go to a local file; the AI never sees them).
3. About to paste a transcript or tool result somewhere? → Skim it for emails/phone/address first, especially if the next destination is cloud-hosted.

## Further reading

- Open Collective personal tokens — Dashboard → For developers (`https://opencollective.com/dashboard/<your-slug>/for-developers`)
- [Open Collective GraphQL v2 docs](https://developers.opencollective.com/access)
- [GDPR Art. 4(1) — definition of personal data](https://gdpr-info.eu/art-4-gdpr/)
