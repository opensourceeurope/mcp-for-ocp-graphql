---
name: exporting-personal-data-locally
description: Use when the user needs personal data from Open Collective (emails, phone numbers, addresses, legalName, payout/billing details on Individual accounts) OR wants a downloadable export/report of OC data as CSV, Markdown, or PDF. Instead of pulling the data through graphql_query — which puts it in the model's context and, for a hosted model, sends it to the provider — you generate a standalone script the user runs themselves. The data flows API → their disk and never passes through the AI.
---

# Exporting Open Collective data locally (keep PII out of the model)

## When to use this

- The user asks for a field that is **personal data**: `email`/`emails`, `phoneNumber`, `address`, `legalName`, or anything inside `payoutMethod`, `paymentMethod`, or `location` on an Individual.
- The user wants a **file** back — a CSV, a Markdown report, or a PDF — of any OC data, personal or not.

For public, aggregate, non-PII answers the user just wants to *read*, keep using `graphql_query` normally (see the `querying-opencollective-graphql` skill). This skill is for when the data should **not** enter the model, or when the deliverable is a downloadable file.

## The principle

Once a personal email lands in a `graphql_query` result, it is in the model's context — for a hosted model that means it has already reached the provider's servers, and you can't take it back. So don't fetch it. **Author a script, hand it over, and let the user run it.** The personal data flows Open Collective API → the user's disk, entirely outside the AI.

## Hard rules

1. **Do NOT call `graphql_query` to fetch the PII yourself.** Use `schema_lookup` / `search_docs` to get the field names and query shape right — those don't return account data — but never run the PII-selecting query through the MCP.
2. **Do NOT run the script yourself** (no Bash, no `uv run`, not even to "test it"). Running it pulls the data back through you. Hand the user the file and the command; they run it.
3. **The token is the user's.** The script reads it from the `OC_PERSONAL_TOKEN` environment variable — never hard-code it, never ask the user to paste it to you, never print it.
4. The script only **queries and writes a file**. It must not send data anywhere else (no upload, no extra network calls).

## How to build it

A working, adaptable template ships at [`resources/export_oc.py`](resources/export_oc.py). Copy it into the user's workspace and customize the three marked blocks to their request:

- **EDIT 1 — `QUERY`**: the read-only GraphQL query. Confirm every field with `schema_lookup` first (mind the inline-fragment gotchas from the querying skill — e.g. `emails` is on `Individual`). For large collections, page with `$limit`/`$offset` until you've collected `totalCount` rows.
- **EDIT 2 — `extract_rows`**: flatten the JSON response into a list of flat `dict` rows.
- **EDIT 3 — `COLUMNS`**: the column order and header labels.

The template uses only the Python standard library for CSV/Markdown; PDF uses `fpdf2`, declared in the script's [PEP 723](https://packaging.python.org/en/latest/specifications/inline-script-metadata/) header so `uv run` installs it automatically — nothing for the user to pip-install.

## Hand-off — what to tell the user

Give them the file and these commands (they need [uv](https://docs.astral.sh/uv/); the MCP setup already relies on it):

```bash
# your token — get one at https://opencollective.com/dashboard/personal-tokens
export OC_PERSONAL_TOKEN='oc_xxx'      # omit for public data only

uv run export_oc.py --slug my-collective --format csv --out admins.csv
uv run export_oc.py --slug my-collective --format md  --out report.md
uv run export_oc.py --slug my-collective --format pdf --out report.pdf
```

`uv run` reads the dependencies from the script header and fetches them on first run. The script prints only a row count and the output path — never the data or the token. Tell the user to open the file to see the results.

If they later want to share the export, remind them to use a channel they already trust for personal data (encrypted email, a password-manager share) — not by pasting it back into a chat with an AI.
