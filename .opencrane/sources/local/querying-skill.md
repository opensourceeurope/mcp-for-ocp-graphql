---
name: querying-opencollective-graphql
description: Use when querying the Open Collective GraphQL MCP (opencollective-graphql-mcp tools such as account, accounts, expenses, host, transactions, me) — for resolving accounts/hosts, counting records, paging, building field selections, or any analysis over Open Collective data. Covers the inline-fragment field gotchas, counting via totalCount, child Project/Event rollup, current-host verification, oversized-result handling, and required tool args.
---

# Querying the Open Collective GraphQL MCP

## Overview

The `opencollective-graphql-mcp` tools are generated from Open Collective's GraphQL schema. Each tool takes a `fields` array that selects what to return, and **nested GraphQL syntax is allowed inside a field string**. These notes capture the non-obvious mechanics so you don't rediscover them every session.

## Quick reference

| Need | How |
|------|-----|
| Resolve an account/host by name | `accounts(searchTerm, …)` — the standalone `search` tool is broken (see #1) |
| Fetch one account | `account(slug \| id \| githubHandle)` |
| List accounts under a host | `accounts(host: [{slug}], type: […], limit, offset, tagSearchOperator)` |
| Count records | query with `limit: 1`, read `totalCount` — never fetch rows just to count |
| Include a parent's Projects/Events | `includeChildrenExpenses: true` |
| Read a field not on base `Account` | wrap in an inline fragment (see #2) |

## Gotchas (each one wasted real time)

**1. The `search` tool is broken** — it errors on unprovided required variables. Use `accounts` with `searchTerm` instead. An empty/error response from `search` is a tool bug, not "no results".

**2. Many fields are NOT on the base `Account` type** and 400 if selected directly. Wrap them in inline fragments inside the `fields` array:
```
"... on AccountWithHost { host { slug name } isApproved }"
"... on AccountWithParent { parent { slug name type } }"
```
The 400 error message lists which fragment type to use — read it and adapt.

**3. Nested selections go inside a single `fields` string**, full GraphQL syntax:
`"members { totalCount, nodes { account { name slug } } }"`. Arguments work too: `"members(role: ADMIN) { … }"`.

**4. To count, use `limit: 1` and read `totalCount`.** Every list tool returns `totalCount` regardless of `limit`. Fetching rows to count wastes tokens and can overflow (see #6).

**5. Required args on list tools.** `expenses` requires `limit`, `offset`, `orderBy`, and `includeChildrenExpenses` on *every* call; `accounts` requires `limit`, `offset`, `tagSearchOperator`. Pass them even for a `limit: 1` count, or the call 400s.

**6. Large results spill to a file** instead of returning inline. When that happens, don't read the whole file into context — query it with `jq`:
```bash
jq -r '.nodes[].account.slug' FILE | sort | uniq -c | sort -rn | head
```
List tools cap at `limit: 1000`; page with `offset` for more. Prefer per-account `totalCount` counts, which sidestep paging entirely.

**7. Accounts have parent/child structure.** A Collective can own Project and Event sub-accounts, each with its own slug. When aggregating, raw high-frequency slugs are often `PROJECT`/`EVENT` children — resolve each with the `AccountWithParent` fragment (#2) and attribute to the parent, then count the parent once with `includeChildrenExpenses: true` to avoid double-counting.

**8. Host-level queries reflect membership *at record time*, not now.** A query filtered by `host` (e.g. `expenses(host: {slug}, hostContext: HOSTED)`) returns records created while the account was under that host — an account that has since **migrated to a different host still shows up.** Before asserting "account X belongs to host Y", confirm the *current* host with `account(X, ["... on AccountWithHost { host { slug } }"])`.

**9. `null` fields can mean "not visible to your persona", not "empty".** The token is the logged-in persona (`me`); field visibility follows its privileges. A field returning `null` for one account but a value for another often signals a permission/ownership difference (e.g. you administer one but not the other) — cross-check with #8 before concluding the data is absent.

**10. Aggregate/metric data lives behind argument-bearing nested fields that the default selection won't surface.** Host analytics — `host.metrics { hostedCollectivesFinancialActivity }`, `hostedCollectivesMembership`, `hostedCollectivesHosting` (and fields like `unhostedAt`, `communityStats`) — each **require an argument**, so they're dropped from the auto-generated `fields` and never appear unless you ask. The tool's `fields` description lists them under **"Some fields require arguments"** with the exact arg name and input type. Pass the argument inline inside the field string:
```
"metrics { hostedCollectivesFinancialActivity(input: { dateRange: { ... }, measures: [ ... ] }) { ... } }"
```
The input object's shape (`dateRange`, `measures`, `bucket`, `groupBy`, `timezone`, …) is the `…MetricsInput` type in the schema; if you guess wrong, the 400 error names the missing/invalid fields. This is the general rule for any nested field with a required arg, not just metrics.

## Personal data — make the user aware before retrieving

Some fields return **personal data** (`emails`, `email`, contact fields on Individual accounts). Retrieving a PII field into a tool result puts it in the model's processing context — for a hosted model that means transmission to the provider's servers, for a local model (Ollama, LM Studio, etc.) it stays on the user's machine. Writing it to a file, commit, log, or message is a further disclosure regardless of where the model runs. These actions cannot be undone — the only control point is before retrieval.

**Default: do not select these fields.** Don't include them silently in a wider selection, and don't have a subagent fetch them.

**When the user asks for PII (or you'd recommend fetching it):**

1. Tell them in plain language what will happen — the data enters the model's context (the provider's servers for a hosted model, their own machine for a local model), and anywhere you then write it (file, commit, message) is a further disclosure either way. If you don't know which kind of model you're running under, say so and let them decide.
2. Once they confirm with that awareness, do what they asked. It's their data and their call; don't second-guess the scope.

If they prefer to keep the data off the model entirely, hand them this command to run in their **own terminal** (output stays local, never enters any agent context):

```bash
# NOT via Claude's `!` prefix — that routes output back through the model.
export OC_TOKEN='<your personal token>'
curl -s https://api.opencollective.com/graphql/v2 \
  -H 'Content-Type: application/json' \
  -H "Personal-Token: $OC_TOKEN" \
  -d '{"query":"query($s:String){account(slug:$s){members(role:ADMIN){nodes{account{name slug emails}}}}}","variables":{"s":"COLLECTIVE_SLUG"}}'
```

This is the repo rule too — see `AGENTS.md` › "Handling Personal Data (PII)".

## Common mistakes

- Treating a `search` error as "no results" → it's the broken tool (#1).
- Selecting `host`/`parent`/`isApproved` on a plain `Account` → 400; needs a fragment (#2).
- Counting by fetching and length-ing rows → use `totalCount` (#4), and remember the required args (#5).
- Reading a spilled result file into context instead of `jq`-ing it (#6).
- Aggregating by raw slug without rolling children into parents (#7) or without checking the current host (#8) → inflated, stale, or mis-attributed totals.
- Expecting host metrics/aggregates in a normal `fields` selection → they need an inline argument and are listed under "Some fields require arguments" in the tool description (#10).
