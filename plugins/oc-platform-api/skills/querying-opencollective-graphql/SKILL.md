---
name: querying-opencollective-graphql
description: Use when querying Open Collective through this repo's MCP (the graphql_query / schema_lookup / search_docs tools) — resolving accounts and hosts, counting records, paging, selecting fields, handling PII, or any analysis over Open Collective data. Covers the read-only proxy model, inline-fragment field gotchas, counting via totalCount, child Project/Event rollup, current-host verification, permission- and scope-shaped nulls, metrics behind argument-bearing fields, enumerating a host's collectives, corpus-wide text scans, searchTerm/tagStats semantics, and where location/country data actually lives (and doesn't).
---

# Querying the Open Collective GraphQL MCP

## Overview

This MCP exposes **three** tools over Open Collective's GraphQL v2 API — there is **no** per-operation tool and no `fields` array. You write **raw GraphQL**:

- **`graphql_query(query, variables=None)`** — runs a **read-only** GraphQL query and returns JSON. Mutations and subscriptions are rejected. `variables` is an optional dict.
- **`schema_lookup(name)`** — exact definition of a type or query field (fields, args with name/type/required/default). Substring matches return candidate names.
- **`search_docs(query, top_k=5)`** — keyword search over the OC docs + a query-field map.

**Workflow: `search_docs` (find the right query/approach) → `schema_lookup` (confirm exact fields, args, required-ness) → `graphql_query` (run it).** Don't guess field names — look them up. `schema_lookup` resolves **types and root query fields only** — for a field nested on an object (`hostedAccounts`, `childrenAccounts`) it returns "no exact match"; look up the type that owns it (`Host`, `Collective`) instead, and expect a long response.

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
| Count a host's collectives+funds | `host(slug: $h) { totalHostedAccounts }` — one number, already excludes children (#9) |
| List a host's hosted collectives | `accounts(host: [{slug: $h}], type: [COLLECTIVE, FUND])`, or `host(slug: $h) { hostedAccounts(accountType: [COLLECTIVE, FUND]) }` (#9) |
| Accounts that JOINED / LEFT a host in a period | `host(slug: $h) { hostedAccounts(joinedBetween: {from, to}) }` / `(isUnhosted: true, unhostedBetween: {from, to})` — top-level accounts only, children never match (#9) |
| How many hostees are actually ALIVE | `hostedAccounts(accountType: [COLLECTIVE, FUND], hadActivityBetween: {from, to})` — the number most reports should lead with |
| Find collectives by tag | probe `tagStats(host: {slug: $h}, tagSearchTerm: $t)` first, then `accounts(tag: [...])` |
| Keyword-scan many accounts' text | page cheap fields, post-process saved results (#10) |
| Convert between currencies | `currencyExchangeRate(requests: [{fromCurrency: USD, toCurrency: EUR}]) { value }` — OC's own rates |
| Split out anonymous donors | `isIncognito` (any Account) + `... on Individual { isGuest }` — both public |
| "Hosted during period X" | `hostedAccounts(joinedBetween:)` + `(isUnhosted: true, unhostedBetween:)` — both public. The per-account `unhostedAt` *field* returns null, but these *filters* work (#9) |
| Find a host's vendors | `accounts(includeVendorsForHost: {slug: $h}, type: [VENDOR])` — vendors never appear in the `host:` filter (#12) |

## The account model — read this before answering anything about a host

Everything in Open Collective is an `Account`. `AccountType` has nine values, and the differences decide what any count means. Read the user's question against this table before querying — "how many projects does our host have" and "how many things does our host host" have different right answers, and users routinely mean the second while saying the first.

| Type | What it is | Appears under a host? |
|---|---|---|
| `COLLECTIVE` | A group/project raising money; the usual unit of "who we host" | **Yes — top level** |
| `FUND` | Pools and redistributes money (grants). Behaves like a Collective, including owning children | **Yes — top level** |
| `PROJECT` | Child of a Collective **or a Fund**, own slug/budget/ledger | Yes, as a child |
| `EVENT` | Child of a Collective, Fund, or the host Organization; time-bound, sells tickets | Yes, as a child |
| `ORGANIZATION` | A company or legal entity — sponsors, and **hosts themselves** | The host's own row (see below), and occasionally a hosted Organization — rare, but real: they show up in departure history, sometimes having left to become their own host |
| `INDIVIDUAL` | A person. The only type carrying emails/PII | **Never** — people relate via roles (admin, contributor, payee) |
| `VENDOR` | A payee entity a host creates for supplier expenses; not a user | **Never in the `host:` filter** — separate query, see #12 |
| `BOT`, `PLATFORM` | Automation; Open Collective itself | No |

**"Host" is a role, not a type.** A host is an `ORGANIZATION` with `isHost: true`. `account(slug: $h)` and `host(slug: $h)` are two GraphQL views of the *same* row (same `id`, `__typename` `Organization` vs `Host`) — use `host(...)` when you want the host-only fields (#9). Because `Organization` does **not** implement `AccountWithHost`, asking a host "who hosts you" through that fragment returns *silently nothing* — no error, no key. That is a quieter failure than #1's usual error message.

**A host appears inside its own hosted-account list.** The lone `ORGANIZATION` in `accounts(host: [{slug: $h}])` is the host itself. Subtract it, or you count the host as one of its own hostees.

**Hierarchy is one level deep.** Top-level accounts (Collective/Fund, plus the host Org) own Projects and Events; those children own nothing further. Every Project and Event has a parent — treat a parentless one as an anomaly worth checking, not a normal case.

**"How big is this host" has five defensible answers.** Pick deliberately and say which you used — an unqualified count is the commonest way to mislead here. The illustrative figures are one host at one moment, shown only for the gaps between them:

| The question actually being asked | Query | e.g. |
|---|---|---|
| How many groups do we host? | `host { totalHostedAccounts }` — COLLECTIVE+FUND, children excluded | 455 |
| How many accounts exist under us? | `accounts(host: [{slug: $h}])` — every type, plus the host's own row | 960 |
| …including archived ones? | `host { hostedAccounts { totalCount } }` (#9) | 968 |
| How many have we *ever* hosted? | add `hostedAccounts(isUnhosted: true)` — departures often rival the current count | +522 |
| How many are actually **alive**? | `hostedAccounts(accountType: [COLLECTIVE, FUND], hadActivityBetween: {from, to})` | 225 of 455 |

That last row is usually the honest headline and the one nobody asks for: roughly half of a host's collectives can be dormant, a wider gap than any of the other distinctions. Vendors sit outside all five (#12).

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

**4. Accounts have parent/child structure.** A Collective **or a Fund** can own Project and Event sub-accounts, each with its own slug; the host Organization itself can own Events directly. When aggregating, resolve children to their parent (`... on AccountWithParent { parent { slug type } }`) and count the parent once with `includeChildrenExpenses: true`, or you double-count / misattribute. Don't assume the parent is a Collective — select `parent { type }` and handle Fund and Organization parents, or those children silently fall out of your rollup. To go the other way (list one account's children) use `childrenAccounts` on the account, or the top-level `accounts(parent: [{slug: $s}])`.

**5. Keep results small.** `graphql_query` returns the JSON inline — a broad selection over a large collection can be enormous. Prefer `totalCount`; page with `limit`/`offset` (collections cap around `limit: 1000`); select only the fields you need.

**6. Host-level queries reflect membership *at record time*, not now.** A query filtered by `host` (e.g. `expenses(host: {slug}, hostContext: HOSTED)`) returns records created while the account was under that host — an account that has since **migrated to another host still shows up**. Before asserting "account X belongs to host Y" today, confirm the *current* host:
```graphql
query($s: String) { account(slug: $s) { ... on AccountWithHost { host { slug } } } }
```
Also: **display names drift; only slugs are stable.** Hosts and collectives get renamed (slug `europe` displays as "Open Source Europe", formerly "Open Collective Europe"). Verify identity by slug; treat a display-name mismatch as a probable rename, not a wrong account.

**7. `null` can mean "not visible to your persona", not "empty".** The token is the logged-in persona (`me`); field visibility follows its privileges. A field that is `null` for one account but populated for another often signals a permission/ownership difference — cross-check with #6 before concluding the data is absent. Don't over-apply this to public profile fields: on a public list scan, `tags: null` or `description: null` just means the collective didn't set one.

Three refinements that tell the cases apart:
- **Shape is diagnostic.** A `null` *object* (`payeeLocation: null`) is a refused permission; an object *full of nulls* (`payeeLocation: {country: null, address: null}`) is a granted permission over data that was never captured. The second is final — no token sees more.
- **Token scopes gate fields independently of role.** A host admin whose personal token lacks the `expenses` scope still gets `null` for `Expense.payeeLocation` and `PayoutMethod.data` — the resolver checks the scope before any role check. When an admin reports "I should see this but don't", suspect a missing scope (Dashboard → For developers → token scopes) before doubting their role.
- **Permission rules aren't in the schema — read the resolver.** `schema_lookup` shows types, never visibility. The API is open source (`opencollective/opencollective-api`, `server/graphql/v2/object/*` and `server/graphql/common/*`); fetching the resolver answers "who can see this" definitively and beats running experiments.

**8. Aggregate/metric data hides behind argument-bearing nested fields.** Host analytics — `host.metrics { hostedCollectivesFinancialActivity }`, `hostedCollectivesMembership`, etc. — each **require an argument**, so they never appear unless you ask with the argument inline:
```graphql
"metrics { hostedCollectivesFinancialActivity(input: { dateRange: {...}, measures: [...] }) { ... } }"
```
`schema_lookup` on the type shows the exact `…MetricsInput` shape; a wrong guess returns a 400 naming the invalid fields. This is the general rule for any nested field with a required arg. Note `host.metrics` itself is admin-gated: it returns `null` (not an error) without a host-admin token, and its membership measures are join/churn *flows*, not a "how many hosted at time T" stock.

**9. Two ways to enumerate a host's accounts — `host.hostedAccounts` is the richer one.** Both work; pick by what you need.

Top-level `accounts` — good for listing and text scans, pages to 250+:
```graphql
query($h: String) {
  accounts(host: [{slug: $h}], type: [COLLECTIVE, FUND], limit: 250, offset: 0) {
    totalCount
    nodes { slug name description tags }
  }
}
```
`host.hostedAccounts` — the same set plus filters `accounts` does not have (`isUnhosted`, `isFrozen`, `isApproved`, `balance`, `consolidatedBalance`, `currencies`, `joinedBetween`, `unhostedBetween`, `hadActivityBetween`, `noActivityBetween`, `searchTerm`, `accountType`, `orderBy`), and `host { totalHostedAccounts }` gives the COLLECTIVE+FUND count as a single number:
```graphql
query($h: String) {
  host(slug: $h) {
    totalHostedAccounts                                  # 455 — collectives + funds only
    hostedAccounts(accountType: [COLLECTIVE], limit: 1) { totalCount }
    left: hostedAccounts(isUnhosted: true, limit: 1) { totalCount }   # 522 — departed accounts
  }
}
```
Three differences that change your numbers:
- **`accounts(host:)` hides some rows by default; `hostedAccounts` doesn't.** Setting `includeArchived: true` on `accounts(host:)` makes the two agree exactly (europe PROJECT: 195 → 201, matching `hostedAccounts(accountType: [PROJECT])`). **Do not report the difference as "these are archived accounts"** — every one of those 201 nodes returns `isArchived: false` and `isActive: true`, so no node-level field explains why the default filter hides them. State the arg, not a cause you can't see.
- `accounts(host:)` **includes the host's own Organization row**; `hostedAccounts` doesn't.
- Only `hostedAccounts` reaches accounts that have **left** (`isUnhosted: true`) or filters by activity/balance.

Two silent filters on `hostedAccounts` to know about: `isApproved` **defaults to `true`**, and the date filters `joinedBetween`/`unhostedBetween` **only match top-level accounts** — they return 0 for `accountType: [PROJECT]` even though 182 projects have left europe. So "27 accounts left in 2025" means 27 budget-holders; children that left with their parent are not counted. Say so rather than implying it covers everything.

Whichever you use, without a `type`/`accountType` filter the result also includes hosted Projects and Events, so the count runs ~2× the number of real budget-holders. Decide whether "collectives" means `[COLLECTIVE]` or `[COLLECTIVE, FUND]`, and say which you used — see the account-model section above for the defensible totals.

**10. Corpus-wide text scans are a legitimate pattern — and result overflow is recoverable.** To keyword-scan every collective under a host, #5's "keep results small" doesn't apply: page through `accounts(...)` selecting only the cheap text fields (`slug name description tags`). A page can exceed the inline token limit — that's fine: the harness saves the oversized result to a file whose path appears in the tool result, and you filter it with `jq`/`grep` instead of re-reading it inline. Do this deliberately rather than shrinking `limit` until it fits. Two rules keep it cheap:
- Scan `description` + `tags` broadly; fetch `longDescription` (large HTML with embedded image markup) **only** for shortlisted slugs — selecting it across hundreds of accounts explodes the result.
- A term that appears *only* in `longDescription` is invisible to the cheap scan — cross-check shortlisting with a `searchTerm` probe (#11) and state the residual coverage gap in your answer.

**11. `searchTerm` is a fuzzy relevance probe, not exhaustive filtering.** Observed behavior: matching is partial/OR-ish (`"open source intelligence"` matched accounts that are merely "open source"), yet a term can return zero hits while related words appear in hosted accounts' descriptions (`"investigation"` → 0 despite "investigate" in profile text). Which fields are indexed, and whether matching stems, is not documented. Use it to *find candidates* and to cross-check a manual scan — never as proof that no match exists. Zero hits ≠ no textual matches.

**12. Vendors are invisible to every host query above.** A host's Vendors (payee entities for supplier expenses) are not returned by `accounts(host: [...])` or `host.hostedAccounts` at any `type` filter. They need their own arg, which does **not** compose with `host:` — passing both silently returns the ordinary hosted list, not vendors:
```graphql
accounts(includeVendorsForHost: {slug: $h}, type: [VENDOR], limit: 1) { totalCount }   # 78 on europe
```
If a question involves everyone a host pays, vendors are a separate query — omitting them understates payees with no error to warn you. One exception to the invisibility: **departed** vendors *do* show up in `hostedAccounts(isUnhosted: true, accountType: [VENDOR])` (6 on europe), which is why an unhosted-account total won't reconcile from Collectives/Funds/Projects/Events alone — Organizations and Vendors make up the remainder.

## Where location/country data lives (verified in the API resolvers)

Recurring ask: "which countries do our contributors / payees come from?" The answer is bounded by design — know the map before promising coverage:

| Source | Who sees it | What it holds |
|--------|-------------|---------------|
| `Individual.location` | The person themselves; others only via a context permission granted in *expense* contexts. **Donors' locations are never visible to the receiving host.** | Profile country — mostly empty in practice |
| `Expense.payeeLocation` | Collective/host admins with the `expenses` scope | Address snapshot taken at submission — **mandatory for INVOICE, blank for RECEIPT** (reimbursements) |
| `PayoutMethod.data` | Same as above | Bank details: Wise-style `details.address.country`, IBAN prefix = bank country. **PayPal = email only, no country** |
| `PaymentMethod.data` | **Only the owning donor's admins** (+ `orders` scope) | Card country exists here but is unreachable for the receiving host — with any token |
| `Order.data` | Nobody — resolver returns `pick(order.data, [])` | — |

Consequences: payee countries are recoverable to ~95% for a host admin (payeeLocation → payout bank details → profile); contributor countries are a structural lower bound (public profiles only) — the real data sits in the host's payment processor (Stripe/PayPal dashboards), outside the API. Always report country stats with their evidence base ("based on N of M payees").

## Personal data — make the user aware before retrieving

Some fields return **personal data** (`email`/`emails` and contact fields on Individual accounts). Selecting a PII field puts it in the model's context — for a hosted model that means transmission to the provider; for a local model it stays on the user's machine. Writing it to a file, commit, log, or message is a further disclosure. These cannot be undone — the only control point is **before** you select the field.

**Default: do not select these fields.** Don't slip them into a wider selection, and don't have a subagent fetch them.

**Files on disk count too.** A local export produced by the export workflow (e.g. `reporting/output/*-admins.csv`) holds the same PII as a query result — reading its data rows with `cat`/`head`/`grep`/Read is the same disclosure as selecting the field, even for an innocent-looking task ("check the structure", "which script made this"). Inspect such files via `head -1` (header) and `wc -l` only, answer content questions from the generating script's code, and for "read me a value from it" requests follow the exporting-personal-data-locally skill: warn, then hand the user a command for their own terminal.

**When the user asks for PII (or you'd recommend it):**
1. Tell them plainly what will happen — the data enters the model's context (provider's servers for a hosted model, their machine for a local one), and anywhere you then write it is a further disclosure. If you don't know which kind of model you're running under, say so.
2. Once they confirm with that awareness, do what they asked — it's their data and their call.

If they'd rather keep it off the model entirely, hand them this to run in their **own terminal** (output stays local; `emails` is on `Individual`, so it needs an inline fragment):
```bash
export OC_TOKEN='<your personal token>'
# -A: Cloudflare in front of the API 403s default curl/python user agents (error 1010)
curl -s https://api.opencollective.com/graphql/v2 \
  -A 'Mozilla/5.0 (compatible; oc-local-export/1.0)' \
  -H 'Content-Type: application/json' \
  -H "Personal-Token: $OC_TOKEN" \
  -d '{"query":"query($s:String){account(slug:$s){members(role:ADMIN){nodes{account{name slug ... on Individual{emails}}}}}}","variables":{"s":"asyncapi"}}' \
| jq -r '["NAME","SLUG","EMAILS"], (.data.account.members.nodes[].account | [.name, .slug, (.emails // [] | join(", "))]) | @tsv' \
| column -t -s $'\t'
```

For a **file export** (CSV / Markdown / PDF), or any larger PII pull, use the **`exporting-personal-data-locally`** skill: you generate a script the user runs themselves, so the data goes API → their disk and never through you.

## Common mistakes

- Expecting a `fields` array or a per-operation tool — there's only `graphql_query` taking raw GraphQL. Use `schema_lookup` to build the selection.
- Selecting `host`/`parent`/`isApproved` on a plain `Account` → error; needs an inline fragment (#1).
- Assuming every `!` arg is mandatory — most have defaults; only `schema_lookup`'s `required: true` args must be supplied (#2).
- Counting by fetching and length-ing rows instead of selecting `totalCount` (#3).
- Aggregating by raw slug without rolling children into parents (#4) or without checking the current host (#6) → inflated, stale, or misattributed totals.
- Expecting host metrics in a normal selection — they need an inline argument (#8).
- Counting a host's "collectives" without a `type` filter, or reaching for `accounts(host:)` when the question needs `hostedAccounts`' filters — departed, frozen, archived, joined-in-period (#9).
- Treating every Project/Event parent as a Collective (Funds and the host Org own children too), or forgetting the host's own Organization row is inside its hosted list (account model section).
- Answering "how many accounts does this host have" with one unqualified number when four defensible ones exist (account model section).
- Omitting Vendors from "everyone this host pays" — no host query returns them (#12).
- Selecting `longDescription` across a whole host's accounts, or trusting a `searchTerm` miss as proof of absence (#10, #11).
- Blaming a role ("but I'm host admin!") for a `null` that a missing token scope causes, or reading an object-of-nulls as hidden data when it means "never captured" (#7).
- Promising contributor-country stats a host admin cannot obtain — donor locations and card countries are unreachable for the receiving host (see the location map).
