# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Yearly stats for a list of Open Collective hosts — run by YOU, never by the AI.

For each host (default: Open Collective Europe Foundation EUR + USD, and Open
Source Europe) over one calendar year (default 2025):

  - total money collected (contributions + added funds; refunds excluded)
  - total money paid out or reimbursed (expenses)
  - number of countries contributors sent money from
  - number of countries payees were paid in
  - unique contributors (with the anonymous guest/incognito share), unique payees
  - hosted collectives: hosted during the year, active during the year
    (>=1 transaction), and hosted at run time

plus a combined all-hosts section (money summed per currency — no FX guessing;
people deduped across hosts), for each of the four headline metrics the top 3
collectives ACROSS all hosts, and the top 3 countries by contributor and by
payee headcount (deduped across hosts). Cross-host money rankings are ordered using Open
Collective's own USD->EUR exchange rate, but amounts are always displayed in the
host's currency.

Every number in the report carries an accuracy note, because the country metrics
are only as good as the underlying visibility:

  - PAYEE countries come from the expense's payee-location snapshot (mandatory
    on invoices), then the payout method's bank details (Wise address / IBAN
    prefix — covers reimbursement-only payees), then the payee's public
    profile. PayPal payout methods store only an email, so PayPal-paid payees
    without an invoice stay countryless. Run with a host-admin
    OC_PERSONAL_TOKEN that has the "expenses" scope enabled — without it the
    API nulls both the snapshots and the payout details even for host admins.
  - CONTRIBUTOR countries are a LOWER BOUND no matter the token: the API only
    exposes a donor's country when their profile makes it public. Payment-card
    countries are never exposed to hosts (verified in the API resolvers — the
    PaymentMethod.data resolver only serves the donor's own admins). The full
    picture lives in the host's payment processor (e.g. Stripe dashboard), not
    in the Open Collective API.

Money and count stats are public and complete even without a token.

Usage, from inside the reporting/ directory (uv fetches deps automatically):

    uv run export_hosts_yearly_stats.py                       # 2025, default hosts
    uv run export_hosts_yearly_stats.py --year 2024
    uv run export_hosts_yearly_stats.py --hosts europe opensource --format csv

Aggregation rules: refund legs are skipped, events/projects roll up into their
parent collective, and the host's own collective is excluded. Unlike
export_top_collectives.py, collectives that migrated to another host after
transacting are INCLUDED (listed on stderr) — the API matches the host at
transaction time, so their records are part of this host's period ledger. "Contributors" counts CONTRIBUTION donors; ADDED_FUNDS
count toward money collected but their source accounts are not treated as
contributors. Output defaults to the gitignored output/ folder next to this
script.
"""

import argparse
import collections
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.opencollective.com/graphql/v2"
PAGE_SIZE = 500
DEFAULT_HOSTS = ["oce-foundation-eur", "oce-foundation-usd", "europe"]

TRANSACTIONS_QUERY = """
query ($slug: String!, $dateFrom: DateTime, $dateTo: DateTime, $limit: Int!, $offset: Int!) {
  transactions(
    host: {slug: $slug}
    kind: [CONTRIBUTION, ADDED_FUNDS, EXPENSE]
    dateFrom: $dateFrom
    dateTo: $dateTo
    limit: $limit
    offset: $offset
  ) {
    totalCount
    nodes {
      type
      kind
      isRefund
      isRefunded
      account {
        slug
        name
        ... on AccountWithHost { host { slug } }
        ... on AccountWithParent {
          parent {
            slug
            name
            ... on AccountWithHost { host { slug } }
          }
        }
      }
      oppositeAccount { slug isIncognito location { country } ... on Individual { isGuest } }
      expense { legacyId account { slug } payeeLocation { country } payoutMethod { type data } }
      amountInHostCurrency { valueInCents currency }
    }
  }
}
"""

HOST_QUERY = """
query ($slug: String!) {
  account(slug: $slug) {
    slug
    name
    ... on Organization { host { currency totalHostedAccounts } }
  }
}
"""

HOSTED_QUERY = """
query ($host: [AccountReferenceInput], $limit: Int!, $offset: Int!) {
  accounts(host: $host, type: [COLLECTIVE, FUND], limit: $limit, offset: $offset) {
    totalCount
    nodes { slug ... on AccountWithHost { approvedAt } }
  }
}
"""

FX_QUERY = """
query ($requests: [CurrencyExchangeRateRequest!]!) {
  currencyExchangeRate(requests: $requests) { value fromCurrency }
}
"""


def have_token() -> bool:
    return bool(os.environ.get("OC_PERSONAL_TOKEN") or os.environ.get("OC_TOKEN"))


def graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("OC_PERSONAL_TOKEN") or os.environ.get("OC_TOKEN")
    headers = {
        "Content-Type": "application/json",
        # Cloudflare fronting the OC API rejects the default Python-urllib
        # user agent with 403 / error 1010.
        "User-Agent": "Mozilla/5.0 (compatible; oc-local-export/1.0)",
    }
    if token:
        headers["Personal-Token"] = token
    body = json.dumps({"query": query, "variables": variables}).encode()
    for attempt in range(6):
        req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                try:
                    # OC sends a fractional Retry-After (e.g. "16.971").
                    wait = float(e.headers.get("Retry-After", 65)) + 1
                except ValueError:
                    wait = 65
                print(f"rate limited (429) — waiting {wait}s "
                      f"(set OC_PERSONAL_TOKEN for higher limits)", file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f"HTTP {e.code} from Open Collective: {e.read().decode(errors='replace')}")
        except urllib.error.URLError as e:
            sys.exit(f"Network error talking to Open Collective: {e.reason}")
    if payload.get("errors"):
        sys.exit("GraphQL errors:\n" + json.dumps(payload["errors"], indent=2))
    return payload.get("data") or {}


def payout_country(payout_method: dict | None) -> str | None:
    """Country from payout details: Wise-style address country, else IBAN prefix.

    PayPal payout methods carry only an email — no country to extract.
    """
    data = (payout_method or {}).get("data") or {}
    details = data.get("details") or {}
    country = data.get("country") or (details.get("address") or {}).get("country")
    if country and isinstance(country, str) and len(country) == 2:
        return country.upper()
    iban = str(details.get("IBAN") or details.get("iban") or "").replace(" ", "")
    if len(iban) >= 2 and iban[:2].isalpha():
        return iban[:2].upper()
    return None


def new_collective(slug: str, name: str, host_slug: str, currency: str) -> dict:
    # "donors"/"payees" map person-slug -> ISO country (or None if unknown),
    # the same shape the host-level dicts use.
    return {
        "slug": slug, "name": name, "host": host_slug, "currency": currency,
        "collected_cents": 0, "paid_cents": 0, "donors": {}, "payees": {},
    }


def fetch_hosted_slugs(slug: str, date_to: str) -> set[str]:
    """Slugs of the host's current collectives approved on/before date_to."""
    slugs: set[str] = set()
    offset = 0
    while True:
        data = graphql(HOSTED_QUERY, {
            "host": [{"slug": slug}], "limit": PAGE_SIZE, "offset": offset})
        coll = data.get("accounts") or {}
        nodes = coll.get("nodes") or []
        for node in nodes:
            approved = node.get("approvedAt") or ""
            # Both are ISO-8601 UTC; day precision is enough here.
            if approved and approved[:10] <= date_to[:10]:
                slugs.add(node["slug"])
        offset += len(nodes)
        if not nodes or offset >= (coll.get("totalCount") or 0):
            return slugs


def fetch_host_stats(slug: str, date_from: str, date_to: str) -> dict:
    """One paginated transactions sweep -> per-host totals + per-collective stats."""
    meta = graphql(HOST_QUERY, {"slug": slug}).get("account") or {}
    if not meta:
        sys.exit(f"Host '{slug}' not found on Open Collective.")
    host_info = meta.get("host") or {}
    host = {
        "slug": slug, "name": meta.get("name") or slug,
        "currency": host_info.get("currency") or "",
        "hosted_current": host_info.get("totalHostedAccounts") or 0,
        "collected_cents": 0, "added_funds_cents": 0, "paid_cents": 0,
        # slug -> ISO country or None; one entry per unique donor/payee.
        "donors": {}, "payees": {},
        "payee_debug": {},  # payee slug -> payout types + a sample expense URL
        "anon_donors": set(),  # donor slugs that are guest or incognito accounts
        "collectives": {},  # slug -> per-collective stats for the top-3 rankings
    }
    departed: set[str] = set()
    offset = 0
    while True:
        data = graphql(TRANSACTIONS_QUERY, {
            "slug": slug, "dateFrom": date_from, "dateTo": date_to,
            "limit": PAGE_SIZE, "offset": offset,
        })
        coll = data.get("transactions") or {}
        nodes = coll.get("nodes") or []
        total = coll.get("totalCount") or 0
        for node in nodes:
            # Skip both legs of a refund so refunded money doesn't count.
            if node.get("isRefund") or node.get("isRefunded"):
                continue
            account = node.get("account") or {}
            # Events and projects roll up into their parent collective.
            account = account.get("parent") or account
            acc_slug = account.get("slug")
            if not acc_slug or acc_slug == slug:
                # The host's own collective is not a hostee.
                continue
            # The API matches the host at transaction time, so these records
            # are part of this host's period ledger even when the collective
            # has since migrated to another host — count them, note them.
            if ((account.get("host") or {}).get("slug") or slug) != slug:
                departed.add(acc_slug)
            amount = node.get("amountInHostCurrency") or {}
            cents = amount.get("valueInCents") or 0
            opposite = node.get("oppositeAccount") or {}
            other = opposite.get("slug")
            profile_country = (opposite.get("location") or {}).get("country")
            entry = host["collectives"].setdefault(acc_slug, new_collective(
                acc_slug, account.get("name") or acc_slug, slug, host["currency"]))
            kind, tx_type = node.get("kind"), node.get("type")
            if kind in ("CONTRIBUTION", "ADDED_FUNDS") and tx_type == "CREDIT":
                host["collected_cents"] += cents
                entry["collected_cents"] += cents
                if kind == "ADDED_FUNDS":
                    host["added_funds_cents"] += cents
                elif other:
                    # Only real contribution donors count as contributors.
                    for donors in (host["donors"], entry["donors"]):
                        donors[other] = donors.get(other) or profile_country
                    if opposite.get("isGuest") or opposite.get("isIncognito"):
                        host["anon_donors"].add(other)
            elif kind == "EXPENSE" and tx_type == "DEBIT":
                host["paid_cents"] += abs(cents)
                entry["paid_cents"] += abs(cents)
                # Country preference: the expense's payee-location snapshot
                # (host-admin visible, mandatory on invoices), then the payout
                # method's bank details (reimbursement-only payees have no
                # snapshot), then the mostly-private profile country.
                expense = node.get("expense") or {}
                country = ((expense.get("payeeLocation") or {}).get("country")
                           or payout_country(expense.get("payoutMethod"))
                           or profile_country)
                if other:
                    for payees in (host["payees"], entry["payees"]):
                        payees[other] = payees.get(other) or country
                    dbg = host["payee_debug"].setdefault(other, {"types": set(), "url": ""})
                    dbg["types"].add((expense.get("payoutMethod") or {}).get("type") or "none")
                    if not dbg["url"] and expense.get("legacyId"):
                        exp_acc = (expense.get("account") or {}).get("slug") or acc_slug
                        dbg["url"] = (f"https://opencollective.com/{exp_acc}"
                                      f"/expenses/{expense['legacyId']}")
        offset += len(nodes)
        print(f"[{slug}] fetched {min(offset, total)}/{total} transaction(s)", file=sys.stderr)
        if not nodes or offset >= total:
            break
        if not have_token():
            time.sleep(0.3)  # be polite to the anonymous rate limit
    if departed:
        print(f"[{slug}] included {len(departed)} account(s) that transacted in the "
              f"period but have since left the host: " + ", ".join(sorted(departed)),
              file=sys.stderr)
    unknown = [p for p, c in host["payees"].items() if not c]
    if unknown:
        # Terminal-only breadcrumbs for manual investigation: the payee's
        # profile, what they were paid with (PayPal/OTHER carry no country
        # data), and one of their expenses to click into.
        print(f"[{slug}] {len(unknown)} payee(s) without country — to investigate:",
              file=sys.stderr)
        for p in sorted(unknown)[:40]:
            dbg = host["payee_debug"].get(p) or {}
            types = "/".join(sorted(dbg.get("types") or {"none"}))
            sample = f"  e.g. {dbg['url']}" if dbg.get("url") else ""
            print(f"  https://opencollective.com/{p} ({types}){sample}", file=sys.stderr)
        if len(unknown) > 40:
            print(f"  ... and {len(unknown) - 40} more", file=sys.stderr)
    # Hosted during the period = current hostees approved on/before the period's
    # end, plus everyone observed transacting under the host in the period (the
    # sweep proves they were hosted then, even if they left since).
    host["hosted_during"] = len(
        fetch_hosted_slugs(slug, date_to) | set(host["collectives"]))
    return host


def fetch_eur_rates(currencies: set[str]) -> dict[str, float]:
    """OC's own FX rates -> EUR, used ONLY to order cross-host money rankings."""
    todo = sorted(c for c in currencies if c and c != "EUR")
    rates = {"EUR": 1.0}
    if not todo:
        return rates
    data = graphql(FX_QUERY, {
        "requests": [{"fromCurrency": c, "toCurrency": "EUR"} for c in todo]})
    for row in data.get("currencyExchangeRate") or []:
        rates[row["fromCurrency"]] = row["value"]
    for c in todo:
        if c not in rates:
            print(f"no EUR rate for {c} — ranking that currency at face value", file=sys.stderr)
            rates[c] = 1.0
    return rates


def money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


def countries(people: dict) -> set[str]:
    return {c for c in people.values() if c}


def based_on(people: dict, who: str) -> str:
    """Accuracy note for a country metric: which share of people it is based on."""
    if not people:
        return f"no {who} in period"
    known = sum(1 for c in people.values() if c)
    return f"based on {known} of {len(people)} {who} ({100 * known / len(people):.0f}%)"


COMPLETE = "complete (public ledger)"
DONOR_CAVEAT = " — lower bound: only public donor profiles carry a country"
PAYEE_NOTE = (" — from expense payee locations and payout bank details "
              "(host admins see all; PayPal payees carry no country)")
ANON_NOTE = " — accounts, not humans: one email can appear as profile + guest + incognito"


def hosted_note(year: int) -> str:
    return (f"current hostees approved by {year}-12-31 + collectives seen "
            f"transacting under the host in {year}; may miss ones that left "
            f"without any {year} transactions")


def host_rows(host: dict, year: int) -> list[tuple[str, str, str]]:
    """(metric, value, accuracy) rows for one host."""
    cur = host["currency"]
    return [
        (f"Money collected ({cur})", money(host["collected_cents"]), COMPLETE),
        (f"— of which added funds ({cur})", money(host["added_funds_cents"]), COMPLETE),
        (f"Money paid out / reimbursed ({cur})", money(host["paid_cents"]), COMPLETE),
        ("Contributor countries", str(len(countries(host["donors"]))),
         based_on(host["donors"], "contributors") + DONOR_CAVEAT),
        ("Payee countries", str(len(countries(host["payees"]))),
         based_on(host["payees"], "payees") + PAYEE_NOTE),
        ("Unique contributors", str(len(host["donors"])), COMPLETE),
        ("— of which anonymous (guest or incognito)", str(len(host["anon_donors"])),
         COMPLETE + ANON_NOTE),
        ("Unique payees (people/orgs paid)", str(len(host["payees"])), COMPLETE),
        (f"Hosted collectives during {year}", str(host["hosted_during"]),
         hosted_note(year)),
        (f"— of which active in {year} (≥1 transaction)",
         str(len(host["collectives"])), COMPLETE),
        ("Hosted collectives at run time", str(host["hosted_current"]), COMPLETE),
    ]


def merged_people(hosts: list[dict], key: str) -> dict[str, str | None]:
    """Dedup donors/payees across hosts; keep a country if any host knows it."""
    merged: dict[str, str | None] = {}
    for h in hosts:
        for who, country in h[key].items():
            merged[who] = merged.get(who) or country
    return merged


def combined_rows(hosts: list[dict], year: int) -> list[tuple[str, str, str]]:
    per_currency: dict[str, dict[str, int]] = {}
    donors = merged_people(hosts, "donors")
    payees = merged_people(hosts, "payees")
    anon: set[str] = set()
    for h in hosts:
        anon |= h["anon_donors"]
        bucket = per_currency.setdefault(h["currency"], {"collected": 0, "paid": 0})
        bucket["collected"] += h["collected_cents"]
        bucket["paid"] += h["paid_cents"]
    rows = []
    for cur in sorted(per_currency):
        rows.append((f"Money collected ({cur})", money(per_currency[cur]["collected"]), COMPLETE))
        rows.append((f"Money paid out ({cur})", money(per_currency[cur]["paid"]), COMPLETE))
    rows += [
        ("Contributor countries (deduped across hosts)", str(len(countries(donors))),
         based_on(donors, "contributors") + DONOR_CAVEAT),
        ("Payee countries (deduped across hosts)", str(len(countries(payees))),
         based_on(payees, "payees") + PAYEE_NOTE),
        ("Unique contributors (deduped across hosts)", str(len(donors)), COMPLETE),
        ("— of which anonymous (guest or incognito)", str(len(anon)),
         COMPLETE + ANON_NOTE),
        ("Unique payees (deduped across hosts)", str(len(payees)), COMPLETE),
        (f"Hosted collectives during {year}",
         str(sum(h["hosted_during"] for h in hosts)), hosted_note(year)),
        (f"— of which active in {year} (≥1 transaction)",
         str(sum(len(h["collectives"]) for h in hosts)), COMPLETE),
        ("Hosted collectives at run time",
         str(sum(h["hosted_current"] for h in hosts)), COMPLETE),
    ]
    return rows


TOP_METRICS = [
    # (title, sort key(collective, rates), value label, value getter, accuracy getter)
    ("Top 3 by money collected",
     lambda c, rates: c["collected_cents"] * rates.get(c["currency"], 1.0),
     "Collected", lambda c: f"{money(c['collected_cents'])} {c['currency']}",
     lambda c: "complete"),
    ("Top 3 by money paid out",
     lambda c, rates: c["paid_cents"] * rates.get(c["currency"], 1.0),
     "Paid out", lambda c: f"{money(c['paid_cents'])} {c['currency']}",
     lambda c: "complete"),
    ("Top 3 by contributor countries",
     lambda c, rates: len(countries(c["donors"])),
     "Countries", lambda c: str(len(countries(c["donors"]))),
     lambda c: based_on(c["donors"], "contributors")),
    ("Top 3 by payee countries",
     lambda c, rates: len(countries(c["payees"])),
     "Countries", lambda c: str(len(countries(c["payees"]))),
     lambda c: based_on(c["payees"], "payees")),
]


def build_top_tables(hosts: list[dict], rates: dict[str, float], top: int = 3) -> list:
    """[(title, header, [(row cells, slug)])] — rankings across ALL hosts."""
    everyone = [c for h in hosts for c in h["collectives"].values()]
    tables = []
    for title, key_fn, label, get, accuracy in TOP_METRICS:
        def key(c, key_fn=key_fn):
            return key_fn(c, rates)
        ranked = sorted((c for c in everyone if key(c)), key=key, reverse=True)[:top]
        header = ["#", "Collective", "Host", label, "Accuracy"]
        rows = [([str(i), c["name"], c["host"], get(c), accuracy(c)], c["slug"])
                for i, c in enumerate(ranked, 1)]
        tables.append((title, header, rows))
    return tables


def build_country_tables(hosts: list[dict], top: int = 3) -> list:
    """Top countries by contributor / payee headcount, deduped across hosts."""
    tables = []
    for key, who, label, caveat in (
            ("donors", "contributors", "Contributors", DONOR_CAVEAT),
            ("payees", "payees", "Payees", PAYEE_NOTE)):
        people = merged_people(hosts, key)
        counter = collections.Counter(c for c in people.values() if c)
        note = based_on(people, who) + caveat
        rows = [([str(i), country, "all", str(n), note], None)
                for i, (country, n) in enumerate(counter.most_common(top), 1)]
        tables.append((f"Top {top} countries by {who}",
                       ["#", "Country", "Host", label, "Accuracy"], rows))
    return tables


def build_sections(hosts: list[dict], year: int) -> list[tuple[str, list[tuple[str, str, str]]]]:
    """[(section title, (metric, value, accuracy) rows)] — one per host + combined."""
    return ([(f"{h['name']} ({h['slug']})", host_rows(h, year)) for h in hosts]
            + [("All hosts combined", combined_rows(hosts, year))])


def write_md(sections, tops, out, title, notes):
    lines = [f"# {title}", ""] + [f"- {n}" for n in notes] + [""]
    for section, rows in sections:
        lines += [f"## {section}", "", "| Metric | Value | Accuracy |", "| --- | --- | --- |"]
        lines += [f"| {m} | {v} | {a} |" for m, v, a in rows]
        lines.append("")
    for section, header, rows in tops:
        lines += [f"## {section}", "", "| " + " | ".join(header) + " |",
                  "| " + " | ".join(["---"] * len(header)) + " |"]
        for row, slug in rows:
            cells = list(row)
            if slug:
                name = cells[1].replace("|", "\\|")
                cells[1] = f"[{name}](https://opencollective.com/{slug})"
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_csv(sections, tops, out, title, notes):
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Section", "Metric or #", "Value", "Accuracy",
                    "Collective", "Collective URL", "Host"])
        for section, rows in sections:
            for m, v, a in rows:
                w.writerow([section, m, v, a, "", "", ""])
        for section, header, rows in tops:
            for row, slug in rows:
                url = f"https://opencollective.com/{slug}" if slug else ""
                w.writerow([section, row[0], row[3], row[4], row[1], url, row[2]])


def write_pdf(sections, tops, out, title, notes):
    from fpdf import FPDF  # from fpdf2, declared in the script header
    from fpdf.fonts import FontFace

    def latin1(text: str) -> str:
        # latin-1 is fpdf's core-font encoding; swap the report's few
        # non-latin-1 characters for ASCII, drop anything else.
        text = text.replace("—", "-").replace("≥", ">=").replace("’", "'")
        return text.encode("latin-1", "replace").decode("latin-1")

    def table(section, header, rows, widths):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, latin1(section), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        # pdf.table() wraps long cell text and handles page breaks — plain
        # cell() rows run off the page with the long accuracy notes.
        with pdf.table(col_widths=widths, first_row_as_headings=True,
                       headings_style=FontFace(emphasis="BOLD")) as t:
            head = t.row()
            for label in header:
                head.cell(latin1(label))
            for cells in rows:
                row = t.row()
                for text in cells:
                    row.cell(latin1(text))

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, latin1(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for n in notes:
        pdf.multi_cell(0, 5, latin1(n), new_x="LMARGIN", new_y="NEXT")
    for section, rows in sections:
        table(section, ["Metric", "Value", "Accuracy"], rows, (34, 14, 52))
    for section, header, rows in tops:
        table(section, header, [row for row, _slug in rows], (5, 25, 15, 15, 40))
    pdf.output(out)


def run() -> None:
    ap = argparse.ArgumentParser(
        description="Yearly money/contributor/country stats for a list of OC hosts.")
    ap.add_argument("--year", type=int, default=2025, help="Calendar year (default: 2025).")
    ap.add_argument("--hosts", nargs="+", default=DEFAULT_HOSTS, metavar="SLUG",
                    help=f"Host slugs (default: {' '.join(DEFAULT_HOSTS)}).")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: output/hosts-yearly-stats-<year>.<format> next to this script).")
    args = ap.parse_args()

    if not have_token():
        print("no OC_PERSONAL_TOKEN set — payee countries need a host-admin token "
              "(expense payee locations are admin-only); money/count stats are fine",
              file=sys.stderr)
    else:
        print("reminder: payee countries need the 'expenses' scope on your token "
              "AND host-admin rights — low payee coverage usually means the scope "
              "is missing (Dashboard -> For developers -> your token)",
              file=sys.stderr)
    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        args.out = os.path.join(out_dir, f"hosts-yearly-stats-{args.year}.{args.format}")

    date_from = f"{args.year}-01-01T00:00:00Z"
    date_to = f"{args.year}-12-31T23:59:59Z"
    hosts = [fetch_host_stats(slug, date_from, date_to) for slug in args.hosts]
    rates = fetch_eur_rates({h["currency"] for h in hosts})
    sections = build_sections(hosts, args.year)
    tops = build_top_tables(hosts, rates) + build_country_tables(hosts)

    title = f"Hosts yearly stats — {args.year}"
    notes = [
        "Hosts: " + ", ".join(f"{h['name']} ({h['slug']}, {h['currency']})" for h in hosts) + ".",
        "Collected = contributions + added funds, refunds excluded. Paid out = expenses "
        "(invoices, reimbursements, grants).",
        "Every number has an Accuracy note. Payee countries use the expense "
        "payee-location snapshot (host admins see nearly all of them). Contributor "
        "countries are a structural lower bound: the API only reveals a donor's "
        "country when their profile is public — payment-card countries are never "
        "exposed to hosts, with any token.",
        "Top-3 money rankings are ordered via Open Collective's USD/EUR rate at run time; "
        "amounts shown in each host's currency.",
    ]
    writer = {"md": write_md, "csv": write_csv, "pdf": write_pdf}[args.format]
    writer(sections, tops, args.out, title, notes)
    print(f"Wrote stats for {len(hosts)} host(s) to {args.out}")


if __name__ == "__main__":
    run()
