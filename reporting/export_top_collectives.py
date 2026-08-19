# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Rank the collectives of a host (default: "europe" / Open Source Europe) over a
period — run by YOU, never by the AI.

Five top-N rankings (default top 10, over the current year up to now):

  1. most financial operations — the "most active" ranking: 40 small expenses
     outrank a single big grant
  2. most money received (contributions)
  3. most distinct donors — 30k from a single donor is not the same as 30k from 300
  4. most money paid out (expenses)
  5. most distinct payees — how many people actually got paid

Usage, from inside the reporting/ directory (uv fetches the deps automatically
from the header above):

    uv run export_top_collectives.py                          # current year -> now
    uv run export_top_collectives.py --month 2026-07          # one calendar month
    uv run export_top_collectives.py --date-from 2025-01-01 --date-to 2025-12-31
    uv run export_top_collectives.py --slug oce --top 20 --format csv
    uv run export_top_collectives.py --month 2026-07 --all   # every active one

--all swaps the rankings for a single census table listing EVERY active
collective, one row each, with all metrics side by side. "Active" is wider
there than in the rankings: at least one financial operation OR at least one
published update in the period, so a collective that only posted an update
still shows up (with zeroes in the money columns).

--date-to is INCLUSIVE: the named day counts in full (it ends at 23:59:59Z), so
--date-from 2025-01-01 --date-to 2025-12-31 really is the whole year. --month
YYYY-MM is a shortcut for a calendar month and cannot be combined with the two
explicit bounds; it also suffixes the output filename with the month, so
successive months do not overwrite each other.

Events and projects are rolled up into their parent collective, so an event's
donations count for the collective running it. Only collectives CURRENTLY
hosted by the host are ranked — ones that migrated to another host mid-period
are skipped (and listed on stderr), even though the API still returns their
transactions from when they were hosted. The host's own collective is excluded
from the rankings too.

All amounts are in the host currency. The data is public, so a token is not
required (set OC_PERSONAL_TOKEN to raise rate limits). Output defaults to the
gitignored output/ folder next to this script.
"""

import argparse
import csv
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.opencollective.com/graphql/v2"
PAGE_SIZE = 500
# Updates are scanned newest-first until the period start, so one page normally
# covers a whole month.
UPDATES_PAGE_SIZE = 100

QUERY = """
query ($slug: String!, $dateFrom: DateTime, $dateTo: DateTime, $limit: Int!, $offset: Int!) {
  transactions(
    host: {slug: $slug}
    kind: [CONTRIBUTION, EXPENSE]
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
      oppositeAccount { slug }
      amountInHostCurrency { valueInCents currency }
    }
  }
}
"""


UPDATES_QUERY = """
query ($host: [AccountReferenceInput], $limit: Int!, $offset: Int!) {
  updates(
    host: $host
    limit: $limit
    offset: $offset
    orderBy: {field: PUBLISHED_AT, direction: DESC}
  ) {
    totalCount
    nodes {
      publishedAt
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
    }
  }
}
"""


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
                    wait = float(e.headers.get("Retry-After") or 0) + 1 or 65
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


def fetch_stats(slug: str, date_from: str, date_to: str) -> tuple[dict, str]:
    """Aggregate per-collective totals from one paginated sweep of transactions.

    Returns ({collective_slug: stats}, host_currency).
    """
    stats: dict[str, dict] = {}
    currency = ""
    skipped: set[str] = set()
    offset = 0
    while True:
        data = graphql(QUERY, {
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
            # Events and projects roll up into their parent collective, so
            # e.g. an event's donations count for the collective running it.
            account = account.get("parent") or account
            acc_slug = account.get("slug")
            if not acc_slug or acc_slug == slug:
                # The host's own collective is not ranked against its hostees.
                continue
            # The API matches the host at transaction time, so collectives that
            # migrated away mid-period still show up — rank only current ones.
            if ((account.get("host") or {}).get("slug") or slug) != slug:
                skipped.add(acc_slug)
                continue
            amount = node.get("amountInHostCurrency") or {}
            cents = amount.get("valueInCents") or 0
            currency = amount.get("currency") or currency
            other = (node.get("oppositeAccount") or {}).get("slug")
            entry = stats.setdefault(acc_slug, {
                "slug": acc_slug, "name": account.get("name") or acc_slug,
                "received_cents": 0, "donors": set(),
                "paid_cents": 0, "payees": set(),
                "operations": 0, "updates": 0,
            })
            # Only the collective-side leg of each transaction is counted, so a
            # single contribution/expense is one operation, not two.
            if node.get("kind") == "CONTRIBUTION" and node.get("type") == "CREDIT":
                entry["received_cents"] += cents
                entry["operations"] += 1
                if other:
                    entry["donors"].add(other)
            elif node.get("kind") == "EXPENSE" and node.get("type") == "DEBIT":
                entry["paid_cents"] += abs(cents)
                entry["operations"] += 1
                if other:
                    entry["payees"].add(other)
        offset += len(nodes)
        print(f"fetched {min(offset, total)}/{total} transaction(s)", file=sys.stderr)
        if not nodes or offset >= total:
            break
        time.sleep(0.3)  # be polite to the API
    if skipped:
        print(f"skipped {len(skipped)} account(s) no longer hosted by '{slug}': "
              + ", ".join(sorted(skipped)), file=sys.stderr)
    return stats, currency


def fetch_updates(slug: str, date_from: str, date_to: str, stats: dict) -> int:
    """Count published updates per collective into `stats`, creating entries for
    collectives that published but never moved money. Returns the total counted.

    The top-level `updates` query has no date filter, so we page newest-first and
    stop as soon as we cross `date_from` — a month is one page in practice.
    """
    counted = 0
    offset = 0
    while True:
        data = graphql(UPDATES_QUERY, {
            "host": [{"slug": slug}], "limit": UPDATES_PAGE_SIZE, "offset": offset,
        })
        coll = data.get("updates") or {}
        nodes = coll.get("nodes") or []
        total = coll.get("totalCount") or 0
        past_period = False
        for node in nodes:
            # publishedAt carries milliseconds ("...:32.842Z") while the bounds do
            # not, and "." sorts below "Z" — so compare on the common
            # YYYY-MM-DDTHH:MM:SS prefix rather than the raw strings.
            published = (node.get("publishedAt") or "")[:19]
            if published < date_from[:19]:
                # Sorted newest-first, so everything after this is older too.
                past_period = True
                break
            if published > date_to[:19]:
                continue
            account = node.get("account") or {}
            # Same roll-up and current-host rules as the transactions sweep, so
            # the two halves of "active" agree on what a collective is.
            account = account.get("parent") or account
            acc_slug = account.get("slug")
            if not acc_slug or acc_slug == slug:
                continue
            if ((account.get("host") or {}).get("slug") or slug) != slug:
                continue
            entry = stats.setdefault(acc_slug, {
                "slug": acc_slug, "name": account.get("name") or acc_slug,
                "received_cents": 0, "donors": set(),
                "paid_cents": 0, "payees": set(),
                "operations": 0, "updates": 0,
            })
            entry["updates"] += 1
            counted += 1
        offset += len(nodes)
        print(f"scanned {min(offset, total)}/{total} update(s)", file=sys.stderr)
        if past_period or not nodes or offset >= total:
            break
        time.sleep(0.3)
    return counted


def money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


RANKINGS = [
    # (title, sort key, [(column label, value getter)])
    # Keep every ranking at exactly two metric columns — the CSV and PDF writers
    # assume a fixed four-column layout.
    ("Top by number of financial operations", lambda s: s["operations"], [
        ("Operations", lambda s: s["operations"]),
        ("Received", lambda s: money(s["received_cents"])),
    ]),
    ("Top by money received", lambda s: s["received_cents"], [
        ("Received", lambda s: money(s["received_cents"])),
        ("Donors", lambda s: len(s["donors"])),
    ]),
    ("Top by number of donors", lambda s: len(s["donors"]), [
        ("Donors", lambda s: len(s["donors"])),
        ("Received", lambda s: money(s["received_cents"])),
    ]),
    ("Top by money paid out", lambda s: s["paid_cents"], [
        ("Paid out", lambda s: money(s["paid_cents"])),
        ("Payees", lambda s: len(s["payees"])),
    ]),
    ("Top by number of payees", lambda s: len(s["payees"]), [
        ("Payees", lambda s: len(s["payees"])),
        ("Paid out", lambda s: money(s["paid_cents"])),
    ]),
]


def build_tables(stats: dict, top: int) -> list[tuple[str, list[str], list[list[str]]]]:
    """Returns [(title, header, rows)] — rows already ranked and truncated to top N."""
    tables = []
    for title, sort_key, columns in RANKINGS:
        ranked = sorted((s for s in stats.values() if sort_key(s)), key=sort_key, reverse=True)[:top]
        header = ["#", "Collective"] + [label for label, _ in columns]
        # Each row is paired with its slug for link rendering in Markdown/CSV.
        rows = [
            ([str(i), s["name"], *[str(get(s)) for _, get in columns]], s["slug"])
            for i, s in enumerate(ranked, 1)
        ]
        tables.append((title, header, rows))
    return tables


# One row per active collective, every metric side by side. Membership is
# "did anything at all happen": a financial operation OR a published update.
ALL_COLUMNS = [
    ("Operations", lambda s: s["operations"]),
    ("Received", lambda s: money(s["received_cents"])),
    ("Donors", lambda s: len(s["donors"])),
    ("Paid out", lambda s: money(s["paid_cents"])),
    ("Payees", lambda s: len(s["payees"])),
    ("Updates", lambda s: s["updates"]),
]


def build_all_table(stats: dict) -> list[tuple[str, list[str], list]]:
    """Returns a single [(title, header, rows)] census of every active collective."""
    active = [s for s in stats.values() if s["operations"] or s["updates"]]
    # A census, not a ranking — the sort is only to make the table readable.
    active.sort(key=lambda s: (-s["operations"], -s["updates"], s["name"].lower()))
    header = ["#", "Collective"] + [label for label, _ in ALL_COLUMNS]
    rows = [
        ([str(i), s["name"], *[str(get(s)) for _, get in ALL_COLUMNS]], s["slug"])
        for i, s in enumerate(active, 1)
    ]
    return [("All active collectives", header, rows)]


def write_csv(tables: list, out: str) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if len(tables) == 1:
            # A single table is written wide — one column per metric — which is
            # what a spreadsheet wants. The long form below only exists because
            # the rankings each carry different metric columns.
            _title, header, rows = tables[0]
            w.writerow([header[0], header[1], "Collective URL", *header[2:]])
            for row, slug in rows:
                w.writerow([row[0], row[1], f"https://opencollective.com/{slug}", *row[2:]])
            return
        w.writerow(["Ranking", "#", "Collective", "Collective URL", "Metric", "Value", "Context metric", "Context value"])
        for title, header, rows in tables:
            for row, slug in rows:
                w.writerow([title, row[0], row[1], f"https://opencollective.com/{slug}",
                            header[2], row[2], header[3], row[3]])


def write_md(tables: list, out: str, title: str, subtitle: str) -> None:
    lines = [f"# {title}", "", subtitle, ""]
    for section, header, rows in tables:
        lines += [f"## {section}", "", "| " + " | ".join(header) + " |",
                  "| " + " | ".join(["---"] * len(header)) + " |"]
        for row, slug in rows:
            cells = list(row)
            name = cells[1].replace("|", "\\|")
            cells[1] = f"[{name}](https://opencollective.com/{slug})"
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# fpdf's core fonts are latin-1 only, and it raises rather than substituting.
# Typographic punctuation (notably the em dash in every report title) is outside
# that range, so fold the common ones to ASCII before falling back to replace.
PDF_TRANSLATION = str.maketrans({
    "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " ",
})


def pdf_text(value: str) -> str:
    """Make `value` safe for fpdf's latin-1 core fonts."""
    return value.translate(PDF_TRANSLATION).encode("latin-1", "replace").decode("latin-1")


def write_pdf(tables: list, out: str, title: str, subtitle: str) -> None:
    from fpdf import FPDF  # from fpdf2, declared in the script header

    # Anything past the ranking tables' four columns needs the extra width.
    widest = max(len(header) for _, header, _ in tables)
    pdf = FPDF(orientation="L" if widest > 4 else "P")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, pdf_text(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    # The --all subtitle is a full sentence; wrap it instead of clipping.
    pdf.multi_cell(0, 5, pdf_text(subtitle), new_x="LMARGIN", new_y="NEXT")
    for section, header, rows in tables:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, pdf_text(section), new_x="LMARGIN", new_y="NEXT")
        # Fixed width per metric column; the name column absorbs the remainder.
        metric_w = 24 if len(header) > 4 else 45
        usable = pdf.w - 2 * pdf.l_margin
        widths = [10, usable - 10 - metric_w * (len(header) - 2)] + [metric_w] * (len(header) - 2)
        pdf.set_font("Helvetica", "B", 8)
        for w, label in zip(widths, header):
            pdf.cell(w, 7, label, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for row, _slug in rows:
            for w, text in zip(widths, row):
                pdf.cell(w, 6, pdf_text(text), border=1)
            pdf.ln()
    pdf.output(out)


def iso_date(value: str) -> str:
    """Period start — the named day counts from 00:00:00Z."""
    try:
        return datetime.date.fromisoformat(value).isoformat() + "T00:00:00Z"
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}")


def iso_date_end(value: str) -> str:
    """Period end — INCLUSIVE, so the named day counts in full, not up to midnight."""
    try:
        return datetime.date.fromisoformat(value).isoformat() + "T23:59:59Z"
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}")


def month_range(value: str) -> tuple[str, str]:
    """'YYYY-MM' -> (first day 00:00:00Z, last day 23:59:59Z) of that calendar month."""
    try:
        first = datetime.date.fromisoformat(value + "-01")
    except ValueError:
        raise ValueError(f"not a YYYY-MM month: {value!r}")
    # Jump into the next month from a day every month has, then step back one day.
    last = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    return first.isoformat() + "T00:00:00Z", last.isoformat() + "T23:59:59Z"


def run() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    ap = argparse.ArgumentParser(description="Rank a host's collectives by financial operations, money received, donors, payouts, and payees — or list every active one with --all.")
    ap.add_argument("--slug", default="europe", help="Host slug (default: europe).")
    ap.add_argument("--date-from", type=iso_date, default=None,
                    help=f"Period start, YYYY-MM-DD (default: {now.year}-01-01).")
    ap.add_argument("--date-to", type=iso_date_end, default=None,
                    help="Period end, YYYY-MM-DD, INCLUSIVE of that day (default: now).")
    ap.add_argument("--month", default=None, metavar="YYYY-MM",
                    help="Whole calendar month, e.g. 2026-07. Cannot be combined with "
                         "--date-from/--date-to; suffixes the output filename with the month.")
    ap.add_argument("--top", type=int, default=10, help="Rows per ranking (default: 10).")
    ap.add_argument("--all", action="store_true",
                    help="Instead of the rankings, list EVERY active collective — one row "
                         "each, with all metrics. Active means at least one financial "
                         "operation or one published update in the period.")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: output/<host-slug>-top-collectives.<format> next to this script).")
    args = ap.parse_args()

    if args.month:
        if args.date_from or args.date_to:
            ap.error("--month cannot be combined with --date-from/--date-to")
        try:
            args.date_from, args.date_to = month_range(args.month)
        except ValueError as e:
            ap.error(str(e))
    if not args.date_from:
        args.date_from = f"{now.year}-01-01T00:00:00Z"
    if not args.date_to:
        args.date_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        # A month run is suffixed so successive months do not overwrite each other.
        suffix = f"-{args.month}" if args.month else ""
        stem = "active-collectives" if args.all else "top-collectives"
        args.out = os.path.join(out_dir, f"{args.slug}-{stem}{suffix}.{args.format}")

    stats, currency = fetch_stats(args.slug, args.date_from, args.date_to)
    if args.all:
        # Only the census needs updates; the rankings are money-only.
        fetch_updates(args.slug, args.date_from, args.date_to, stats)
        tables = build_all_table(stats)
    else:
        tables = build_tables(stats, args.top)

    period = f"{args.date_from[:10]} to {args.date_to[:10]}"
    if args.all:
        title = f"Active collectives — {args.slug} host"
        subtitle = (f"Period: {period}. Every collective with at least one financial operation "
                    f"or published update. Amounts in {currency or 'host currency'}. "
                    f"Refunded transactions excluded; events and projects roll up into their "
                    f"parent; only collectives currently hosted by '{args.slug}' are listed.")
    else:
        title = f"Top collectives — {args.slug} host"
        subtitle = f"Period: {period}. Amounts in {currency or 'host currency'}. Refunded transactions excluded."
    if args.format == "csv":
        write_csv(tables, args.out)
    elif args.format == "md":
        write_md(tables, args.out, title, subtitle)
    else:
        write_pdf(tables, args.out, title, subtitle)

    unit = "collective(s)" if args.all else "row(s)"
    scope = "table" if args.all else "ranking(s)"
    print(f"Wrote {sum(len(rows) for _, _, rows in tables)} {unit} across {len(tables)} {scope} to {args.out}")


if __name__ == "__main__":
    run()
