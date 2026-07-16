# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Export Open Collective data to a local file — run by the USER, never by the AI.

The data flows Open Collective API -> your disk. It never passes through the AI
that generated this script: the agent writes the query, YOU run the script with
YOUR token, and the results land in a file the agent never reads.

Usage (uv fetches the deps automatically from the header above):

    export OC_PERSONAL_TOKEN='<your token from https://opencollective.com/dashboard/personal-tokens>'
    uv run export_oc.py --slug my-collective --format csv --out admins.csv
    uv run export_oc.py --slug my-collective --format md  --out admins.md
    uv run export_oc.py --slug my-collective --format pdf --out admins.pdf

Anonymous (public data only): omit OC_PERSONAL_TOKEN.

--------------------------------------------------------------------------------
AGENT: customize the three marked blocks below (QUERY, extract_rows, COLUMNS) to
the user's request, then hand the file over. Do NOT run it yourself, and do NOT
fetch the data through graphql_query — that would defeat the purpose.
--------------------------------------------------------------------------------
"""

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.opencollective.com/graphql/v2"

# ── EDIT 1/3 — the GraphQL query ────────────────────────────────────────────
# Default: the ADMIN members (name + email) of one collective. Replace with the
# query the user asked for. Keep it read-only. For large collections, page with
# $limit/$offset and loop until you've collected `totalCount` rows (see run()).
QUERY = """
query ($slug: String) {
  account(slug: $slug) {
    slug
    name
    members(role: ADMIN, limit: 100) {
      totalCount
      nodes {
        account {
          name
          slug
          ... on Individual { emails }
        }
      }
    }
  }
}
"""


# ── EDIT 2/3 — turn the JSON response into a flat list of rows ───────────────
def extract_rows(data: dict) -> list[dict]:
    account = (data or {}).get("account") or {}
    rows = []
    for member in (account.get("members") or {}).get("nodes") or []:
        acc = member.get("account") or {}
        emails = acc.get("emails") or []
        rows.append(
            {
                "name": acc.get("name") or "",
                "slug": acc.get("slug") or "",
                "email": ", ".join(emails),
            }
        )
    return rows


# ── EDIT 3/3 — the columns (order + header labels) ───────────────────────────
COLUMNS = [("name", "Name"), ("slug", "Slug"), ("email", "Email")]
# ─────────────────────────────────────────────────────────────────────────────


def graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("OC_PERSONAL_TOKEN") or os.environ.get("OC_TOKEN")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Personal-Token"] = token
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from Open Collective: {e.read().decode(errors='replace')}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error talking to Open Collective: {e.reason}")
    if payload.get("errors"):
        sys.exit("GraphQL errors:\n" + json.dumps(payload["errors"], indent=2))
    return payload.get("data") or {}


def write_csv(rows: list[dict], out: str) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in COLUMNS])
        for r in rows:
            w.writerow([r.get(key, "") for key, _ in COLUMNS])


def write_md(rows: list[dict], out: str, title: str) -> None:
    labels = [label for _, label in COLUMNS]
    lines = [f"# {title}", "", "| " + " | ".join(labels) + " |", "| " + " | ".join(["---"] * len(labels)) + " |"]
    for r in rows:
        cells = [str(r.get(key, "")).replace("|", "\\|") for key, _ in COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", f"_{len(rows)} row(s)._", ""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_pdf(rows: list[dict], out: str, title: str) -> None:
    from fpdf import FPDF  # from fpdf2, declared in the script header

    pdf = FPDF(orientation="L")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    labels = [label for _, label in COLUMNS]
    col_w = (pdf.w - pdf.l_margin - pdf.r_margin) / len(labels)
    pdf.set_font("Helvetica", "B", 10)
    for label in labels:
        pdf.cell(col_w, 8, label, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for r in rows:
        for key, _ in COLUMNS:
            text = str(r.get(key, ""))
            # latin-1 is fpdf's core-font encoding; drop anything outside it.
            pdf.cell(col_w, 7, text.encode("latin-1", "replace").decode("latin-1"), border=1)
        pdf.ln()
    pdf.output(out)


def run() -> None:
    ap = argparse.ArgumentParser(description="Export Open Collective data to a local file.")
    ap.add_argument("--slug", required=True, help="Collective slug to query.")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="csv")
    ap.add_argument("--out", required=True, help="Output file path.")
    args = ap.parse_args()

    data = graphql(QUERY, {"slug": args.slug})
    rows = extract_rows(data)

    title = f"Open Collective export — {args.slug}"
    if args.format == "csv":
        write_csv(rows, args.out)
    elif args.format == "md":
        write_md(rows, args.out, title)
    else:
        write_pdf(rows, args.out, title)

    # Only a count + path is printed — never the data or the token.
    print(f"Wrote {len(rows)} row(s) to {args.out}")


if __name__ == "__main__":
    run()
