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

The **Token** column says what an anonymous run gives you and what needs a token.

| Script | What it does | Token | How to run / output |
| --- | --- | --- | --- |
| `export_europe_admins.py` | Full list of collectives hosted by a host (default `europe`): creation date, last donation, last financial operation, and every admin with emails, social links, address, country. | **Needed** — `account` + `transactions` scopes; runs anonymously but then all personal fields and activity columns come back empty. | `OC_PERSONAL_TOKEN=oc_xxx uv run export_europe_admins.py`<br>Options: `--format csv`/`pdf`, `--slug <host>`, `--out <path>`.<br><br>**Output:** `output/<host-slug>-admins.{md,csv,pdf}`, default `…/europe-admins.md` |
| `export_collectives_admins.py` | Admins (+ emails, social links, country) for a chosen list of collectives — pass slugs as arguments (generate a shortlist with `export_top_collectives.py` first). Python rewrite of the old `oc-admins.mjs`. | **Needed** — runs anonymously but then all personal fields come back empty. | `OC_PERSONAL_TOKEN=oc_xxx uv run export_collectives_admins.py <slug> [slug ...]`<br>Options: `--format csv`/`pdf`, `--out <path>`.<br><br>**Output:** `output/collectives-admins.{md,csv,pdf}`, default `…/collectives-admins.md` |
| `export_never_active_collectives.py` | Every collective of a host that never had any activity — not a single financial operation or published update, including in its events/projects — with creation date, oldest first. Archived ones are marked; the host itself is excluded. | **Not needed** — public data; set one only to raise rate limits. | `uv run export_never_active_collectives.py`<br>Options: `--slug <host>`, `--format csv`/`pdf`, `--out <path>`.<br><br>**Output:** `output/<host-slug>-never-active.{md,csv,pdf}`, default `…/europe-never-active.md` |
| `export_top_collectives.py` | Four top-10 rankings of a host's collectives over a period (default: current year → now): most money received, most distinct donors, most money paid out, most distinct payees. Events/projects roll up into their parent collective. | **Not needed** — public data; set one only to raise rate limits. | `uv run export_top_collectives.py`<br>Options: `--slug <host>`, `--date-from`/`--date-to YYYY-MM-DD`, `--top <n>`, `--format csv`/`pdf`, `--out <path>`.<br><br>**Output:** `output/<host-slug>-top-collectives.{md,csv,pdf}`, default `…/europe-top-collectives.md` |
| `export_hosts_yearly_stats.py` | Yearly stats for a list of hosts (default: Open Collective Europe Foundation EUR + USD, Open Source Europe; year 2025): money collected (contributions + added funds) and paid out per host, contributor/payee country counts, unique contributors and payees, hosted-collective counts, an all-hosts combined section, and cross-host top-3 collectives per metric. | **Partial** — money and count stats are public; the country stats need a token with host-admin rights (individual locations are admin-only), coverage % is reported so you can judge them. | `uv run export_hosts_yearly_stats.py`<br>Options: `--year <yyyy>`, `--hosts <slug> [slug ...]`, `--format csv`/`pdf`, `--out <path>`.<br><br>**Output:** `output/hosts-yearly-stats-<year>.{md,csv,pdf}` |

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
