---
name: exporting-personal-data-locally
description: Use when the user needs personal data from Open Collective (emails, phone numbers, addresses, legalName, payout/billing details on Individual accounts) OR wants a downloadable export/report of OC data as CSV, Markdown, or PDF — AND whenever about to read, inspect, grep, verify, or answer a question from an already-generated export file (anything under reporting/output/ or produced by an export script), even for an innocent-looking task like "check the file structure" or "which script made this". Instead of pulling the data through graphql_query — which puts it in the model's context and, for a hosted model, sends it to the provider — you generate a standalone script the user runs themselves. The data flows API → their disk and never passes through the AI.
---

# Exporting Open Collective data locally (keep PII out of the model)

## When to use this

- The user asks for a field that is **personal data**: `email`/`emails`, `phoneNumber`, `address`, `legalName`, or anything inside `payoutMethod`, `paymentMethod`, or `location` on an Individual.
- The user wants a **file** back — a CSV, a Markdown report, or a PDF — of any OC data, personal or not.
- You are about to **touch an existing export file** — read it, grep it, describe its structure, verify a run worked, or answer "what's in it". The rules below apply to those files, not only to new queries.

For public, aggregate, non-PII answers the user just wants to *read*, keep using `graphql_query` normally (see the `querying-opencollective-graphql` skill). This skill is for when the data should **not** enter the model, or when the deliverable is a downloadable file.

## The principle

Once a personal email lands in a `graphql_query` result, it is in the model's context — for a hosted model that means it has already reached the provider's servers, and you can't take it back. So don't fetch it. **Author a script, hand it over, and let the user run it.** The personal data flows Open Collective API → the user's disk, entirely outside the AI.

## Hard rules

1. **Do NOT call `graphql_query` to fetch the PII yourself.** Use `schema_lookup` / `search_docs` to get the field names and query shape right — those don't return account data — but never run the PII-selecting query through the MCP.
2. **Do NOT run the script yourself** (no Bash, no `uv run`, not even to "test it"). Running it pulls the data back through you. Hand the user the file and the command; they run it.
3. **The token is the user's.** The script reads it from the `OC_PERSONAL_TOKEN` environment variable — never hard-code it, never ask the user to paste it to you, never print it.
4. The script only **queries and writes a file**. It must not send data anywhere else (no upload, no extra network calls).
5. **Always send a real `User-Agent` header on the request.** Cloudflare sits in front of the API and 403s Python's default urllib user agent with `error code: 1010`, so the export fails before it starts. The template already sets `"User-Agent": "Mozilla/5.0 (compatible; oc-local-export/1.0)"` — if you customize, rewrite, or hand-roll the request, keep that header. This is the single most common reason a generated export script fails on first run.
6. **Do NOT read a generated export's data rows back into context** — no `cat`/`head`/`tail`/`grep`/Read over a PII-bearing export, not even to "check the structure" or "confirm it worked". A row on disk is the user's; a row in your context has reached the provider's servers and is in the transcript forever — reading it *is* the disclosure the whole workflow exists to prevent. What you may do instead:
   - structure/verification questions → `head -1` (header line) and `wc -l` only, plus the generating script's `COLUMNS`/code;
   - "give me X's email, it's already in the CSV" → don't read it out; warn per the querying skill's PII flow and hand them the command for **their** terminal, e.g. `grep -i '<name>' reporting/output/<file>.csv`;
   - "it's the user's own export", "it's just one row", "the file is local anyway" — all mean STOP: header only, command hand-off.

## How to build it

A working, adaptable template ships at [`resources/export_oc.py`](resources/export_oc.py). Copy it into the user's workspace and customize the three marked blocks to their request:

- **EDIT 1 — `QUERY`**: the read-only GraphQL query. Confirm every field with `schema_lookup` first (mind the inline-fragment gotchas from the querying skill — e.g. `emails` is on `Individual`). For large collections, page with `$limit`/`$offset` until you've collected `totalCount` rows.
- **EDIT 2 — `extract_rows`**: flatten the JSON response into a list of flat `dict` rows.
- **EDIT 3 — `COLUMNS`**: the column order and header labels.

The template uses only the Python standard library for CSV/Markdown; PDF uses `fpdf2`, declared in the script's [PEP 723](https://packaging.python.org/en/latest/specifications/inline-script-metadata/) header so `uv run` installs it automatically — nothing for the user to pip-install.

**Where to put it:** if the user's workspace keeps a maintained export-scripts index — a `reporting/` folder whose README holds a table of scripts, outputs, and run commands — save the script there, default its output into the gitignored `reporting/output/`, and add a row to that table. Otherwise put the script where the user asked and let them pick the output path.

## Hand-off — what to tell the user

Give them the file and these commands (they need [uv](https://docs.astral.sh/uv/); the MCP setup already relies on it):

```bash
# your token — create one under Dashboard → For developers
# (https://opencollective.com/dashboard/<your-slug>/for-developers)
export OC_PERSONAL_TOKEN='oc_xxx'      # omit for public data only

uv run export_oc.py --slug my-collective --format csv --out admins.csv
uv run export_oc.py --slug my-collective --format md  --out report.md
uv run export_oc.py --slug my-collective --format pdf --out report.pdf
```

`uv run` reads the dependencies from the script header and fetches them on first run. The script prints only a row count and the output path — never the data or the token. Tell the user to open the file to see the results.

If they later want to share the export, remind them to use a channel they already trust for personal data (encrypted email, a password-manager share) — not by pasting it back into a chat with an AI.
