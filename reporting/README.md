# Reporting

Standalone data-export scripts, kept separate from repo tooling (that lives in
[`../scripts/`](../scripts/)). They write into [`output/`](output/), which is
**gitignored on purpose**: the exports contain personal data (emails, addresses) of
real people, and must never be committed, shared via untrusted channels, or pasted
into a chat with an AI.

Personal tokens come from your Open Collective Dashboard → **For developers**
(`https://opencollective.com/dashboard/<your-slug>/for-developers`). Scope and
host-admin rights on the token decide which personal fields come back non-empty.

**Work on reports from inside this directory** — `cd reporting` first. All commands
below assume it is your working directory.

| Script | What it does | How to run / output |
| --- | --- | --- |
| `export_europe_admins.py` | Full list of collectives hosted by a host (default `europe`): creation date, last donation, last financial operation, and every admin with emails, social links, address, country. | `OC_PERSONAL_TOKEN=oc_xxx uv run export_europe_admins.py`<br>Options: `--format csv`/`pdf`, `--slug <host>`, `--out <path>`. Token needs the `account` **and** `transactions` scopes.<br><br>**Output:** `output/<host-slug>-admins.{md,csv,pdf}`, default `…/europe-admins.md` |
| `export_collectives_admins.py` | Admins (+ emails, social links, country) for a chosen list of collectives — pass slugs as arguments (generate a shortlist with `export_top_collectives.py` first). Python rewrite of the old `oc-admins.mjs`. | `OC_PERSONAL_TOKEN=oc_xxx uv run export_collectives_admins.py <slug> [slug ...]`<br>Options: `--format csv`/`pdf`, `--out <path>`.<br><br>**Output:** `output/collectives-admins.{md,csv,pdf}`, default `…/collectives-admins.md` |
| `export_top_collectives.py` | Four top-10 rankings of a host's collectives over a period (default: current year → now): most money received, most distinct donors, most money paid out, most distinct payees. Public data — no token needed. | `uv run export_top_collectives.py`<br>Options: `--slug <host>`, `--date-from`/`--date-to YYYY-MM-DD`, `--top <n>`, `--format csv`/`pdf`, `--out <path>`.<br><br>**Output:** `output/<host-slug>-top-collectives.{md,csv,pdf}`, default `…/europe-top-collectives.md` |

## Conventions for new export scripts

- One self-contained file per export, with a [PEP 723](https://packaging.python.org/en/latest/specifications/inline-script-metadata/)
  header so `uv run` resolves dependencies — nothing to install.
- Read the token from `OC_PERSONAL_TOKEN` (fallback `OC_TOKEN`); never hard-code it,
  never print it.
- Default the output into `output/` (resolved relative to the script file, so it works
  from any working directory); print only a row count and the output path.
- Send a real `User-Agent` header — Cloudflare in front of `api.opencollective.com`
  rejects default python/curl agents with HTTP 403 / error 1010.
- Add the script to the table above.
