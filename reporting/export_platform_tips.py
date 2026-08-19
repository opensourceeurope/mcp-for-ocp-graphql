# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Platform-tip report for any Open Collective fiscal host or collective, any period.

A "platform tip" is the optional extra a donor adds for Open Collective itself on
top of their contribution. This script answers, for a chosen host (or a chosen
list of collectives) over a chosen period:

  - how many contribution charges there were, how many carried a tip, and the share
  - how much was tipped, per currency, plus the average tip
  - the same broken down by month (or year)
  - which collectives generated the most tips
  - how donors picked the tip (the percentage-of-contribution distribution)

WHO GETS THE MONEY: nobody's host does. The tip is revenue for Open Collective's
own entity (`ofitech`). On hosts whose OWN payment processor collects the money a
second `PLATFORM_TIP_DEBT` transaction pair is written, crediting the host for cash
it owes the platform — a liability in transit, never host income. Hosts whose
contributions run through the platform's processor have no such pair at all.

That is why this script does NOT count `PLATFORM_TIP*` transactions under a
`host:` filter. Those legs are booked against `ofitech` (or no host), so the
host-filtered query returns a flat 0 for platform-processor hosts even though
their collectives are being tipped. Instead it pages the contribution charges and
sums `Order.platformTipAmount`, the per-charge tip, which is present under both
models. For hosts that do have debt rows the report also prints the debt-route
figure as an independent cross-check.

Usage, from inside the reporting/ directory (uv fetches deps automatically):

    uv run export_platform_tips.py                                  # europe, current year
    uv run export_platform_tips.py --slug raft --date-from 2026-01-01
    uv run export_platform_tips.py --slug giftcollective --group-by year
    uv run export_platform_tips.py --collective postmarketos microcosm
    uv run export_platform_tips.py --slug europe --format csv

Accuracy notes carried into the report: refunded contributions are excluded but a
separately refunded tip is not; amounts are summed per currency and never
FX-converted; "contributions" means individual charges, so a monthly donor counts
once per month; and children (events/projects) roll up into their parent.

No personal data is queried or written — output is safe to share, unlike the other
exports in this directory.
"""

import argparse
import collections
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

CHARGES_QUERY = """
query ($host: AccountReferenceInput, $accounts: [AccountReferenceInput!],
       $includeChildren: Boolean!, $dateFrom: DateTime, $dateTo: DateTime,
       $limit: Int!, $offset: Int!) {
  transactions(
    host: $host
    account: $accounts
    kind: [CONTRIBUTION]
    type: CREDIT
    isRefund: false
    includeChildrenTransactions: $includeChildren
    dateFrom: $dateFrom
    dateTo: $dateTo
    limit: $limit
    offset: $offset
  ) {
    totalCount
    nodes {
      createdAt
      account {
        slug
        name
        ... on AccountWithParent { parent { slug name } }
      }
      order {
        amount { valueInCents currency }
        platformTipAmount { valueInCents currency }
      }
    }
  }
}
"""

# Independent cross-check, only meaningful for hosts that collect tips themselves.
DEBT_QUERY = """
query ($slug: String!, $dateFrom: DateTime, $dateTo: DateTime) {
  account(slug: $slug) {
    slug
    name
    currency
    stats {
      totalAmountReceived(kind: [PLATFORM_TIP_DEBT], dateFrom: $dateFrom, dateTo: $dateTo) {
        valueInCents
        currency
      }
    }
  }
  rows: transactions(
    host: {slug: $slug}
    kind: [PLATFORM_TIP_DEBT]
    type: CREDIT
    includeDebts: true
    isRefund: false
    dateFrom: $dateFrom
    dateTo: $dateTo
    limit: 1
  ) {
    totalCount
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


def bucket_of(created_at: str, group_by: str) -> str:
    """'2026-08-19T…' -> '2026-08' (month) or '2026' (year)."""
    return created_at[:7] if group_by == "month" else created_at[:4]


def fetch(host: str | None, collectives: list[str], date_from: str, date_to: str,
          group_by: str) -> dict:
    """One paginated sweep over contribution charges, aggregating tips as we go."""
    agg = {
        "charges": 0,
        "tipped": 0,
        "by_currency": collections.defaultdict(lambda: {"tipped": 0, "cents": 0}),
        "by_period": collections.defaultdict(lambda: {"charges": 0, "tipped": 0,
                                                      "cents": collections.Counter()}),
        "by_account": collections.defaultdict(lambda: {"name": "", "tipped": 0,
                                                       "cents": collections.Counter()}),
        "pct": collections.Counter(),
        "pct_sampled": 0,
    }
    variables = {
        "host": {"slug": host} if host else None,
        "accounts": [{"slug": s} for s in collectives] or None,
        # Only in collective mode: under a host filter the children are already
        # separate hosted accounts, so rolling them in again double-counts.
        "includeChildren": bool(collectives),
        "dateFrom": date_from,
        "dateTo": date_to,
        "limit": PAGE_SIZE,
        "offset": 0,
    }
    total = None
    while True:
        page = graphql(CHARGES_QUERY, variables)["transactions"]
        if total is None:
            total = page["totalCount"]
            print(f"{total} contribution charge(s) to sweep…", file=sys.stderr)
        nodes = page["nodes"] or []
        for node in nodes:
            order = node.get("order") or {}
            tip = order.get("platformTipAmount") or {}
            # platformTipAmount is null as well as 0 for untipped charges.
            cents = tip.get("valueInCents") or 0
            currency = tip.get("currency") or "?"
            period = bucket_of(node["createdAt"], group_by)

            account = node.get("account") or {}
            parent = account.get("parent") or {}
            # Roll events/projects up into the collective that owns them.
            slug = parent.get("slug") or account.get("slug") or "?"
            name = parent.get("name") or account.get("name") or slug

            agg["charges"] += 1
            agg["by_period"][period]["charges"] += 1
            acc = agg["by_account"][slug]
            acc["name"] = name
            if cents > 0:
                agg["tipped"] += 1
                agg["by_currency"][currency]["tipped"] += 1
                agg["by_currency"][currency]["cents"] += cents
                agg["by_period"][period]["tipped"] += 1
                agg["by_period"][period]["cents"][currency] += cents
                acc["tipped"] += 1
                acc["cents"][currency] += cents

                gross = order.get("amount") or {}
                # A percentage only means anything when both sides are one currency.
                if gross.get("valueInCents") and gross.get("currency") == currency:
                    agg["pct"][round(cents / gross["valueInCents"] * 100, 1)] += 1
                    agg["pct_sampled"] += 1

        variables["offset"] += PAGE_SIZE
        if variables["offset"] >= total or not nodes:
            break
        print(f"  …{min(variables['offset'], total)}/{total}", file=sys.stderr)
    return agg


def money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


def per_currency(counter: collections.Counter) -> str:
    if not counter:
        return "-"
    return ", ".join(f"{money(c)} {cur}" for cur, c in sorted(counter.items()))


def pct(part: int, whole: int) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "-"


def build_tables(agg: dict, debt: dict | None, top: int,
                 group_by: str) -> list[tuple[str, list[str], list[list[str]]]]:
    tables = []

    rows = [
        ["Contribution charges", str(agg["charges"])],
        ["Charges with a tip", str(agg["tipped"])],
        ["Share tipped", pct(agg["tipped"], agg["charges"])],
    ]
    for currency, d in sorted(agg["by_currency"].items()):
        rows.append([f"Tips totalled ({currency})", f"{money(d['cents'])} {currency}"])
        rows.append([f"Average tip ({currency})",
                     f"{money(round(d['cents'] / d['tipped']))} {currency}"
                     if d["tipped"] else "-"])
    if not agg["by_currency"]:
        rows.append(["Tips totalled", "none in this period"])
    tables.append(("Summary", ["Metric", "Value"], rows))

    label = "Month" if group_by == "month" else "Year"
    period_rows = [
        [period, str(d["charges"]), str(d["tipped"]),
         pct(d["tipped"], d["charges"]), per_currency(d["cents"])]
        for period, d in sorted(agg["by_period"].items())
    ]
    tables.append((f"By {label.lower()}",
                   [label, "Charges", "Tipped", "Share", "Tips"], period_rows))

    ranked = sorted(
        agg["by_account"].items(),
        key=lambda kv: (sum(kv[1]["cents"].values()), kv[1]["tipped"]),
        reverse=True,
    )
    account_rows = [
        [str(i), d["name"], slug, str(d["tipped"]), per_currency(d["cents"])]
        for i, (slug, d) in enumerate(ranked[:top], 1)
        if d["tipped"]
    ]
    tables.append((f"Top {top} accounts by tips",
                   ["#", "Account", "Slug", "Tipped charges", "Tips"], account_rows))

    if agg["pct_sampled"]:
        pct_rows = [
            [f"{share}%", str(n), pct(n, agg["pct_sampled"])]
            for share, n in agg["pct"].most_common(10)
        ]
        tables.append((
            f"How donors picked the tip ({agg['pct_sampled']} charges where tip and "
            f"contribution share one currency)",
            ["Tip as % of contribution", "Charges", "Share"], pct_rows))

    if debt is not None:
        tables.append((
            "Cross-check: the host's own PLATFORM_TIP_DEBT ledger",
            ["Metric", "Value"],
            [
                ["Debt rows (tips this host's processor collected)", str(debt["rows"])],
                ["Debt total (converted to host currency)",
                 f"{money(debt['cents'])} {debt['currency']}" if debt["rows"] else "-"],
                ["Reads as 0 rows?",
                 "yes — this host's tips are collected by the platform's processor, "
                 "so no debt is recorded. NOT an absence of tips."
                 if not debt["rows"] else "no"],
            ]))

    return tables


def write_csv(tables: list, out: str) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for title, header, rows in tables:
            w.writerow([title])
            w.writerow(header)
            w.writerows(rows)
            w.writerow([])


def write_md(tables: list, out: str, title: str, notes: list[str]) -> None:
    lines = [f"# {title}", ""]
    for section, header, rows in tables:
        lines += [f"## {section}", "", "| " + " | ".join(header) + " |",
                  "| " + " | ".join(["---"] * len(header)) + " |"]
        for row in rows:
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
        lines.append("")
    lines += ["## Accuracy notes", ""] + [f"- {n}" for n in notes] + [""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_pdf(tables: list, out: str, title: str, notes: list[str]) -> None:
    from fpdf import FPDF  # from fpdf2, declared in the script header

    def latin(text: str) -> str:
        # latin-1 is fpdf's core-font encoding; drop anything outside it.
        return text.encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    # multi_cell(w=0) measures from the CURRENT x, so an explicit width plus an
    # explicit cursor reset is the only way to survive a preceding table row.
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    def para(text: str, size: int, style: str = "") -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(usable, size * 0.55 + 2, latin(text),
                       new_x="LMARGIN", new_y="NEXT")

    para(title, 14, "B")
    for section, header, rows in tables:
        pdf.ln(3)
        para(section, 10, "B")
        widths = [usable / max(len(header), 1)] * len(header)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_x(pdf.l_margin)
        for w, cell in zip(widths, header):
            pdf.cell(w, 6, latin(cell)[:38], border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for row in rows:
            pdf.set_x(pdf.l_margin)
            for w, cell in zip(widths, row):
                pdf.cell(w, 6, latin(cell)[:38], border=1)
            pdf.ln()
    pdf.ln(4)
    para("Accuracy notes", 10, "B")
    for note in notes:
        para(f"- {note}", 8)
    pdf.output(out)


def iso_date(value: str) -> str:
    try:
        return datetime.date.fromisoformat(value).isoformat() + "T00:00:00Z"
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}")


def run() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    ap = argparse.ArgumentParser(
        description="Platform tips for a fiscal host or a set of collectives, over a period.")
    ap.add_argument("--slug", default=None,
                    help="Host slug — reports every collective it hosts (default: europe).")
    ap.add_argument("--collective", nargs="+", default=None, metavar="SLUG",
                    help="One or more collective slugs instead of a whole host "
                         "(their events/projects are included).")
    ap.add_argument("--date-from", type=iso_date, default=None,
                    help=f"Period start, YYYY-MM-DD (default: {now.year}-01-01).")
    ap.add_argument("--date-to", type=iso_date, default=None,
                    help="Period end, YYYY-MM-DD (default: now).")
    ap.add_argument("--group-by", choices=["month", "year"], default="month",
                    help="Time breakdown granularity (default: month).")
    ap.add_argument("--top", type=int, default=15,
                    help="Rows in the per-account ranking (default: 15).")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output path (default: output/<target>-platform-tips.<format> "
                         "next to this script).")
    args = ap.parse_args()

    if args.slug and args.collective:
        sys.exit("Pass --slug (a host) or --collective (specific accounts), not both.")
    if not args.collective and not args.slug:
        args.slug = "europe"

    date_from = args.date_from or f"{now.year}-01-01T00:00:00Z"
    date_to = args.date_to or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    target = args.slug or "-".join(args.collective[:3])

    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        args.out = os.path.join(out_dir, f"{target}-platform-tips.{args.format}")

    agg = fetch(args.slug, args.collective or [], date_from, date_to, args.group_by)

    debt = None
    if args.slug:
        data = graphql(DEBT_QUERY, {"slug": args.slug, "dateFrom": date_from,
                                    "dateTo": date_to})
        account = data.get("account") or {}
        received = ((account.get("stats") or {}).get("totalAmountReceived")) or {}
        debt = {
            "rows": (data.get("rows") or {}).get("totalCount") or 0,
            "cents": received.get("valueInCents") or 0,
            "currency": received.get("currency") or account.get("currency") or "",
        }

    tables = build_tables(agg, debt, args.top, args.group_by)

    scope = (f"host {args.slug}" if args.slug
             else "collectives " + ", ".join(args.collective))
    title = (f"Platform tips — {scope} — {date_from[:10]} to {date_to[:10]}")
    notes = [
        "Platform tips are revenue for Open Collective's own entity (ofitech), NOT income "
        "for the fiscal host. Where a PLATFORM_TIP_DEBT pair exists it credits the host "
        "for cash it owes the platform — a liability in transit.",
        "Totals come from Order.platformTipAmount summed over individual contribution "
        "charges, the only route that works whether or not the host's own processor "
        "collects tips.",
        "Amounts are grouped by their own currency and never FX-converted; the "
        "cross-check figure is the API's own conversion to host currency.",
        "\"Charges\" are individual payments, so a monthly recurring donor counts once "
        "per month rather than once per subscription.",
        "Refunded contributions are excluded. A tip refunded on its own is still counted "
        "(the debt-route cross-check likewise has no refund filter).",
        "Events and projects roll up into their parent collective.",
        "Built from host-filtered transactions, so coverage of collectives that have "
        "since left the host is not guaranteed — verify before claiming full history.",
        "No personal data is queried; this output is safe to share.",
    ]

    if args.format == "csv":
        write_csv(tables, args.out)
    elif args.format == "md":
        write_md(tables, args.out, title, notes)
    else:
        write_pdf(tables, args.out, title, notes)

    print(f"{agg['tipped']} of {agg['charges']} charge(s) tipped "
          f"({pct(agg['tipped'], agg['charges'])}) — wrote {args.out}")


if __name__ == "__main__":
    run()
