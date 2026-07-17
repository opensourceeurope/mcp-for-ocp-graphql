# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Rank the collectives of a host (default: "europe" / Open Source Europe) over a
period — run by YOU, never by the AI.

Four top-N rankings (default top 10, over the current year up to now):

  1. most money received (contributions)
  2. most distinct donors — 30k from a single donor is not the same as 30k from 300
  3. most money paid out (expenses)
  4. most distinct payees — how many people actually got paid

Usage, from inside the reporting/ directory (uv fetches the deps automatically
from the header above):

    uv run export_top_collectives.py                          # current year -> now
    uv run export_top_collectives.py --date-from 2025-01-01 --date-to 2025-12-31
    uv run export_top_collectives.py --slug oce --top 20 --format csv

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
            })
            if node.get("kind") == "CONTRIBUTION" and node.get("type") == "CREDIT":
                entry["received_cents"] += cents
                if other:
                    entry["donors"].add(other)
            elif node.get("kind") == "EXPENSE" and node.get("type") == "DEBIT":
                entry["paid_cents"] += abs(cents)
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


def money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


RANKINGS = [
    # (title, sort key, [(column label, value getter)])
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


def write_csv(tables: list, out: str) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
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


def write_pdf(tables: list, out: str, title: str, subtitle: str) -> None:
    from fpdf import FPDF  # from fpdf2, declared in the script header

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, subtitle, new_x="LMARGIN", new_y="NEXT")
    for section, header, rows in tables:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, section, new_x="LMARGIN", new_y="NEXT")
        widths = [10, 90, 45, 45]
        pdf.set_font("Helvetica", "B", 8)
        for w, label in zip(widths, header):
            pdf.cell(w, 7, label, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for row, _slug in rows:
            for w, text in zip(widths, row):
                # latin-1 is fpdf's core-font encoding; drop anything outside it.
                pdf.cell(w, 6, text.encode("latin-1", "replace").decode("latin-1"), border=1)
            pdf.ln()
    pdf.output(out)


def iso_date(value: str) -> str:
    try:
        return datetime.date.fromisoformat(value).isoformat() + "T00:00:00Z"
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}")


def run() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    ap = argparse.ArgumentParser(description="Rank a host's collectives by money received, donors, payouts, and payees.")
    ap.add_argument("--slug", default="europe", help="Host slug (default: europe).")
    ap.add_argument("--date-from", type=iso_date, default=None,
                    help=f"Period start, YYYY-MM-DD (default: {now.year}-01-01).")
    ap.add_argument("--date-to", type=iso_date, default=None,
                    help="Period end, YYYY-MM-DD (default: now).")
    ap.add_argument("--top", type=int, default=10, help="Rows per ranking (default: 10).")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: output/<host-slug>-top-collectives.<format> next to this script).")
    args = ap.parse_args()

    if not args.date_from:
        args.date_from = f"{now.year}-01-01T00:00:00Z"
    if not args.date_to:
        args.date_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        args.out = os.path.join(out_dir, f"{args.slug}-top-collectives.{args.format}")

    stats, currency = fetch_stats(args.slug, args.date_from, args.date_to)
    tables = build_tables(stats, args.top)

    period = f"{args.date_from[:10]} to {args.date_to[:10]}"
    title = f"Top collectives — {args.slug} host"
    subtitle = f"Period: {period}. Amounts in {currency or 'host currency'}. Refunded transactions excluded."
    if args.format == "csv":
        write_csv(tables, args.out)
    elif args.format == "md":
        write_md(tables, args.out, title, subtitle)
    else:
        write_pdf(tables, args.out, title, subtitle)

    print(f"Wrote {sum(len(rows) for _, _, rows in tables)} row(s) across {len(tables)} ranking(s) to {args.out}")


if __name__ == "__main__":
    run()
