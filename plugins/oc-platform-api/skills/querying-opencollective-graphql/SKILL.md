---
name: querying-opencollective-graphql
description: Use when querying Open Collective through this repo's MCP (the graphql_query / schema_lookup / search_docs tools) — resolving accounts and hosts, counting records, paging, selecting fields, handling PII, or any analysis over Open Collective data. Covers the read-only proxy model, inline-fragment field gotchas, counting via totalCount, child Project/Event rollup, current-host verification, permission-shaped nulls, and metrics behind argument-bearing fields.
---

# Querying the Open Collective GraphQL MCP

## Overview

This MCP exposes **three** tools over Open Collective's GraphQL v2 API — there is **no** per-operation tool and no `fields` array. You write **raw GraphQL**:

- **`graphql_query(query, variables=None)`** — runs a **read-only** GraphQL query and returns JSON. Mutations and subscriptions are rejected. `variables` is an optional dict.
- **`schema_lookup(name)`** — exact definition of a type or query field (fields, args with name/type/required/default). Substring matches return candidate names.
- **`search_docs(query, top_k=5)`** — semantic search over the OC docs + a query-field map.

**Workflow: `search_docs` (find the right query/approach) → `schema_lookup` (confirm exact fields, args, required-ness) → `graphql_query` (run it).** Don't guess field names — look them up.

## Quick reference

| Need | How |
|------|-----|
| Discover which query/fields to use | `search_docs("list expenses for a collective")` |
| Confirm a type/field's exact shape + required args | `schema_lookup("expenses")`, `schema_lookup("Account")` |
| Fetch one account | `account(slug: $s)` — args: `slug`, `id`, or `githubHandle` |
| Resolve/search accounts by name | `accounts(searchTerm: $q, limit: 5)` |
| Count records | select `totalCount` with `limit: 1` — never fetch rows to count (#3) |
| Read a field not on base `Account` | inline fragment (#1) |
| Roll a parent's Projects/Events into one total | `includeChildrenExpenses: true` (#4) |

## Gotchas (each one wastes real time)

**1. Many fields are NOT on the base `Account` type** and error if selected directly. Wrap them in inline fragments:
```graphql
query($s: String) {
  account(slug: $s) {
    slug name
    ... on AccountWithHost { host { slug name } isApproved }
    ... on AccountWithParent { parent { slug name type } }
  }
}
```
The error message names the fragment type to use — read it and adapt. Use `schema_lookup` to confirm which interface a field lives on.

**2. Only truly-required args must be supplied — trust `schema_lookup`, not the `!`.** An arg errors only if it is `NON_NULL` **and has no default**. Many args that look mandatory (e.g. `accounts`' `limit`/`offset`/`tagSearchOperator` are `Int!`/enum!) actually carry defaults, so you can omit them. `schema_lookup(name)` reports `required: true/false` per arg (it already accounts for defaults) — that flag is the source of truth, not the type's `!`.

**3. To count, select `totalCount`, don't fetch rows.** Collections expose `totalCount` independent of how many nodes you request:
```graphql
query($s: String) { account(slug: $s) { expenses(limit: 1) { totalCount } } }
```
Fetching rows just to length them wastes tokens and can produce huge results (#5).

**4. Accounts have parent/child structure.** A Collective can own Project and Event sub-accounts, each with its own slug. When aggregating, resolve children to their parent (`... on AccountWithParent { parent { slug } }`) and count the parent once with `includeChildrenExpenses: true`, or you double-count / misattribute.

**5. Keep results small.** `graphql_query` returns the JSON inline — a broad selection over a large collection can be enormous. Prefer `totalCount`; page with `limit`/`offset` (collections cap around `limit: 1000`); select only the fields you need.

**6. Host-level queries reflect membership *at record time*, not now.** A query filtered by `host` (e.g. `expenses(host: {slug}, hostContext: HOSTED)`) returns records created while the account was under that host — an account that has since **migrated to another host still shows up**. Before asserting "account X belongs to host Y" today, confirm the *current* host:
```graphql
query($s: String) { account(slug: $s) { ... on AccountWithHost { host { slug } } } }
```

**7. `null` can mean "not visible to your persona", not "empty".** The token is the logged-in persona (`me`); field visibility follows its privileges. A field that is `null` for one account but populated for another often signals a permission/ownership difference — cross-check with #6 before concluding the data is absent.

**8. Aggregate/metric data hides behind argument-bearing nested fields.** Host analytics — `host.metrics { hostedCollectivesFinancialActivity }`, `hostedCollectivesMembership`, etc. — each **require an argument**, so they never appear unless you ask with the argument inline:
```graphql
"metrics { hostedCollectivesFinancialActivity(input: { dateRange: {...}, measures: [...] }) { ... } }"
```
`schema_lookup` on the type shows the exact `…MetricsInput` shape; a wrong guess returns a 400 naming the invalid fields. This is the general rule for any nested field with a required arg.

## Personal data — make the user aware before retrieving

Some fields return **personal data** (`email`/`emails` and contact fields on Individual accounts). Selecting a PII field puts it in the model's context — for a hosted model that means transmission to the provider; for a local model it stays on the user's machine. Writing it to a file, commit, log, or message is a further disclosure. These cannot be undone — the only control point is **before** you select the field.

**Default: do not select these fields.** Don't slip them into a wider selection, and don't have a subagent fetch them.

**When the user asks for PII (or you'd recommend it):**
1. Tell them plainly what will happen — the data enters the model's context (provider's servers for a hosted model, their machine for a local one), and anywhere you then write it is a further disclosure. If you don't know which kind of model you're running under, say so.
2. Once they confirm with that awareness, do what they asked — it's their data and their call.

If they'd rather keep it off the model entirely, hand them this to run in their **own terminal** (output stays local):
```bash
export OC_TOKEN='<your personal token>'
curl -s https://api.opencollective.com/graphql/v2 \
  -H 'Content-Type: application/json' \
  -H "Personal-Token: $OC_TOKEN" \
  -d '{"query":"query($s:String){account(slug:$s){members(role:ADMIN){nodes{account{name slug emails}}}}}","variables":{"s":"COLLECTIVE_SLUG"}}'
```
This is the repo rule too — see `AGENTS.md` › "Handling Personal Data (PII)".

## Common mistakes

- Expecting a `fields` array or a per-operation tool — there's only `graphql_query` taking raw GraphQL. Use `schema_lookup` to build the selection.
- Selecting `host`/`parent`/`isApproved` on a plain `Account` → error; needs an inline fragment (#1).
- Assuming every `!` arg is mandatory — most have defaults; only `schema_lookup`'s `required: true` args must be supplied (#2).
- Counting by fetching and length-ing rows instead of selecting `totalCount` (#3).
- Aggregating by raw slug without rolling children into parents (#4) or without checking the current host (#6) → inflated, stale, or misattributed totals.
- Expecting host metrics in a normal selection — they need an inline argument (#8).
