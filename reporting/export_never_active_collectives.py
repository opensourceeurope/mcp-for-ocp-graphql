# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""List every collective of a host (default: "europe" / Open Source Europe)
that never had any activity — run by YOU, never by the AI.

"Never had any activity" means not a single financial operation (donation,
expense, fees, ...) and not a single published update — including in the
collective's events and projects, so a collective whose event was active does
NOT qualify. The table shows each collective's creation date, oldest first.
Archived collectives are marked. The host's own collective is excluded.

Usage, from inside the reporting/ directory (uv fetches the deps automatically
from the header above):

    uv run export_never_active_collectives.py
    uv run export_never_active_collectives.py --slug oce --format csv

The data is public, so a token is not required (set OC_PERSONAL_TOKEN to raise
rate limits). Output defaults to the gitignored output/ folder next to this
script.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.opencollective.com/graphql/v2"
# Each collective node carries nested transactions/updates/children lookups,
# so keep pages small or the API response gets slow enough to time out.
PAGE_SIZE = 25

QUERY = """
query ($host: [AccountReferenceInput], $limit: Int!, $offset: Int!) {
  accounts(host: $host, type: [COLLECTIVE], limit: $limit, offset: $offset) {
    totalCount
    nodes {
      name
      slug
      isArchived
      createdAt
      lastFinOp: transactions(limit: 1, includeChildrenTransactions: true) {
        nodes { createdAt kind type }
      }
      lastUpdate: updates(limit: 1, onlyPublishedUpdates: true, orderBy: {field: PUBLISHED_AT, direction: DESC}) {
        nodes { publishedAt }
      }
      childrenAccounts(limit: 100) {
        nodes {
          lastUpdate: updates(limit: 1, onlyPublishedUpdates: true, orderBy: {field: PUBLISHED_AT, direction: DESC}) {
            nodes { publishedAt }
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
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 5:
                reason = getattr(e, "reason", e)
                print(f"network error ({reason}) — retrying in 10s", file=sys.stderr)
                time.sleep(10)
                continue
            sys.exit(f"Network error talking to Open Collective: {getattr(e, 'reason', e)}")
    if payload.get("errors"):
        sys.exit("GraphQL errors:\n" + json.dumps(payload["errors"], indent=2))
    return payload.get("data") or {}


def fetch_collectives(slug: str) -> list[dict]:
    collectives = []
    offset = 0
    while True:
        data = graphql(QUERY, {"host": [{"slug": slug}], "limit": PAGE_SIZE, "offset": offset})
        coll = data.get("accounts") or {}
        nodes = coll.get("nodes") or []
        total = coll.get("totalCount") or 0
        for node in nodes:
            if node.get("slug") == slug:  # the host's own collective is not ranked
                continue
            had_fin_op = bool((node.get("lastFinOp") or {}).get("nodes"))
            # A published update (by the collective or one of its events/projects)
            # counts as activity too.
            update_dates = [
                ((u.get("nodes") or [{}])[0].get("publishedAt") or "")[:10]
                for u in [node.get("lastUpdate") or {}]
                + [c.get("lastUpdate") or {} for c in (node.get("childrenAccounts") or {}).get("nodes") or []]
            ]
            if had_fin_op or any(update_dates):
                continue  # had some activity — not listed
            name = node.get("name") or node.get("slug") or ""
            if node.get("isArchived"):
                name += " (archived)"
            collectives.append({
                "slug": node.get("slug") or "",
                "name": name,
                "created": (node.get("createdAt") or "")[:10],
            })
        offset += len(nodes)
        print(f"fetched {min(offset, total)}/{total} collective(s)", file=sys.stderr)
        if not nodes or offset >= total:
            break
        time.sleep(0.3)  # be polite to the API
    collectives.sort(key=lambda c: c["created"])  # oldest first
    return collectives


HEADER = ["#", "Collective", "Created"]


def to_rows(collectives: list[dict]) -> list[tuple[list[str], str]]:
    return [
        ([str(i), c["name"], c["created"]], c["slug"])
        for i, c in enumerate(collectives, 1)
    ]


def write_csv(rows: list, out: str) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER + ["Collective URL"])
        for row, slug in rows:
            w.writerow(row + [f"https://opencollective.com/{slug}"])


def write_md(rows: list, out: str, title: str) -> None:
    lines = [f"# {title}", "", "| " + " | ".join(HEADER) + " |",
             "| " + " | ".join(["---"] * len(HEADER)) + " |"]
    for row, slug in rows:
        cells = list(row)
        name = cells[1].replace("|", "\\|")
        cells[1] = f"[{name}](https://opencollective.com/{slug})"
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_pdf(rows: list, out: str, title: str) -> None:
    from fpdf import FPDF  # from fpdf2, declared in the script header

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    widths = [10, 120, 30]
    pdf.set_font("Helvetica", "B", 8)
    for w, label in zip(widths, HEADER):
        pdf.cell(w, 7, label, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for row, _slug in rows:
        for w, text in zip(widths, row):
            # latin-1 is fpdf's core-font encoding; drop anything outside it.
            pdf.cell(w, 6, text.encode("latin-1", "replace").decode("latin-1"), border=1)
        pdf.ln()
    pdf.output(out)


def run() -> None:
    ap = argparse.ArgumentParser(description="List a host's collectives that never had any activity (no transactions, no updates).")
    ap.add_argument("--slug", default="europe", help="Host slug (default: europe).")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: output/<host-slug>-never-active.<format> next to this script).")
    args = ap.parse_args()

    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        args.out = os.path.join(out_dir, f"{args.slug}-never-active.{args.format}")

    collectives = fetch_collectives(args.slug)
    rows = to_rows(collectives)

    title = f"Collectives that never had any activity — {args.slug} host"
    if args.format == "csv":
        write_csv(rows, args.out)
    elif args.format == "md":
        write_md(rows, args.out, title)
    else:
        write_pdf(rows, args.out, title)

    print(f"Wrote {len(rows)} row(s) to {args.out}")


if __name__ == "__main__":
    run()
