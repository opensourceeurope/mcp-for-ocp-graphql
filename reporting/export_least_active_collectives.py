# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Rank the least active collectives of a host (default: "europe" / Open Source
Europe) — run by YOU, never by the AI.

"Least active" means the oldest last financial operation of any kind (donation,
expense, fees, ...); collectives that never had one rank first. The table shows
each collective's creation date and its last activity. Archived collectives are
marked. The host's own collective is excluded.

Usage, from inside the reporting/ directory (uv fetches the deps automatically
from the header above):

    uv run export_least_active_collectives.py              # 10 least active
    uv run export_least_active_collectives.py --top 20
    uv run export_least_active_collectives.py --slug oce --format csv

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
PAGE_SIZE = 50

QUERY = """
query ($host: [AccountReferenceInput], $limit: Int!, $offset: Int!) {
  accounts(host: $host, type: [COLLECTIVE], limit: $limit, offset: $offset) {
    totalCount
    nodes {
      name
      slug
      isArchived
      createdAt
      lastFinOp: transactions(limit: 1) {
        nodes { createdAt kind type }
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
            fin_ops = (node.get("lastFinOp") or {}).get("nodes") or []
            fin_op = fin_ops[0] if fin_ops else {}
            last_date = (fin_op.get("createdAt") or "")[:10]
            detail = " ".join(x for x in (fin_op.get("kind"), fin_op.get("type")) if x)
            name = node.get("name") or node.get("slug") or ""
            if node.get("isArchived"):
                name += " (archived)"
            collectives.append({
                "slug": node.get("slug") or "",
                "name": name,
                "created": (node.get("createdAt") or "")[:10],
                "last_date": last_date,
                "last_activity": f"{last_date} ({detail})" if last_date and detail
                                 else (last_date or "never"),
            })
        offset += len(nodes)
        print(f"fetched {min(offset, total)}/{total} collective(s)", file=sys.stderr)
        if not nodes or offset >= total:
            break
        time.sleep(0.3)  # be polite to the API
    # Least active first: never-active collectives, then oldest last activity;
    # ties broken by creation date (oldest first).
    collectives.sort(key=lambda c: (c["last_date"] or "0000-00-00", c["created"]))
    return collectives


HEADER = ["#", "Collective", "Created", "Last activity"]


def to_rows(collectives: list[dict], top: int) -> list[tuple[list[str], str]]:
    return [
        ([str(i), c["name"], c["created"], c["last_activity"]], c["slug"])
        for i, c in enumerate(collectives[:top], 1)
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
    widths = [10, 80, 30, 70]
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
    ap = argparse.ArgumentParser(description="Rank a host's least active collectives (oldest last financial operation first).")
    ap.add_argument("--slug", default="europe", help="Host slug (default: europe).")
    ap.add_argument("--top", type=int, default=10, help="Number of rows (default: 10).")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: output/<host-slug>-least-active.<format> next to this script).")
    args = ap.parse_args()

    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        args.out = os.path.join(out_dir, f"{args.slug}-least-active.{args.format}")

    collectives = fetch_collectives(args.slug)
    rows = to_rows(collectives, args.top)

    title = f"Least active collectives — {args.slug} host"
    if args.format == "csv":
        write_csv(rows, args.out)
    elif args.format == "md":
        write_md(rows, args.out, title)
    else:
        write_pdf(rows, args.out, title)

    print(f"Wrote {len(rows)} row(s) to {args.out}")


if __name__ == "__main__":
    run()
