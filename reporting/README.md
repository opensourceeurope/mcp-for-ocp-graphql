# Reporting

Standalone data-export scripts, kept separate from repo tooling (that lives in
[`../scripts/`](../scripts/)). They write into [`output/`](output/), which is
**gitignored on purpose**: the exports contain personal data (emails, addresses) of
real people, and must never be committed, shared via untrusted channels, or pasted
into a chat with an AI.

Personal tokens come from your Open Collective Dashboard → **For developers**
(`https://opencollective.com/dashboard/<your-slug>/for-developers`). Scope and
host-admin rights on the token decide which personal fields come back non-empty.

| Script | What it does | How to run / output |
| --- | --- | --- |
| `export_europe_admins.py` | Full list of collectives hosted by a host (default `europe`): creation date, last donation, last financial operation, and every admin with emails, social links, address, country. | `OC_PERSONAL_TOKEN=oc_xxx uv run reporting/export_europe_admins.py`<br>Options: `--format csv`/`pdf`, `--slug <host>`, `--out <path>`. Token needs the `account` **and** `transactions` scopes.<br><br>**Output:** `reporting/output/<host-slug>-admins.{md,csv,pdf}`, default `…/europe-admins.md` |
| `export_collectives_admins.py` | Admins (+ emails, social links, country) for a chosen list of collectives — pass slugs as arguments, or use the baked-in list of top `europe`-host collectives. Python rewrite of the old `oc-admins.mjs`. | `OC_PERSONAL_TOKEN=oc_xxx uv run reporting/export_collectives_admins.py [slug ...]`<br>Options: `--format csv`/`pdf`, `--out <path>`.<br><br>**Output:** `reporting/output/collectives-admins.{md,csv,pdf}`, default `…/collectives-admins.md` |

## Conventions for new export scripts

- One self-contained file per export, with a [PEP 723](https://packaging.python.org/en/latest/specifications/inline-script-metadata/)
  header so `uv run` resolves dependencies — nothing to install.
- Read the token from `OC_PERSONAL_TOKEN` (fallback `OC_TOKEN`); never hard-code it,
  never print it.
- Default the output into `reporting/output/`; print only a row count and the output path.
- Send a real `User-Agent` header — Cloudflare in front of `api.opencollective.com`
  rejects default python/curl agents with HTTP 403 / error 1010.
- Add the script to the table above.
