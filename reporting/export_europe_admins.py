# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Export all collectives hosted by a host (default: "europe" / Open Source Europe)
with their admins and the admins' personal data — run by YOU, never by the AI.

The data flows Open Collective API -> your disk. It never passes through the AI
that generated this script: the agent wrote the query, YOU run the script with
YOUR token, and the results land in a file the agent never reads.

Usage (uv fetches the deps automatically from the header above):

    export OC_PERSONAL_TOKEN='<your token — Dashboard → For developers>'
    uv run reporting/export_europe_admins.py                 # -> reporting/output/europe-admins.md
    uv run reporting/export_europe_admins.py --format csv    # -> reporting/output/europe-admins.csv
    uv run reporting/export_europe_admins.py --format pdf --out /tmp/report.pdf

The token needs the "account" and "transactions" scopes. Output defaults to the
repo's gitignored reporting/output/ folder.

Personal fields (email, address) are only populated for accounts your token is
allowed to see — as a host admin you should see them for hosted-collective
admins; otherwise they come back blank.
"""

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.opencollective.com/graphql/v2"
_WARNED: set[str] = set()

# One page of hosted collectives (type COLLECTIVE) with their ADMIN members.
# Per collective: the newest incoming contribution (lastDonation) and the newest
# financial operation of any kind (lastFinOp). Personal fields live on the
# Individual type, hence the inline fragment.
QUERY = """
query ($host: [AccountReferenceInput], $limit: Int!, $offset: Int!) {
  accounts(host: $host, type: [COLLECTIVE], limit: $limit, offset: $offset) {
    totalCount
    nodes {
      name
      slug
      isArchived
      createdAt
      lastDonation: transactions(limit: 1, type: CREDIT, kind: [CONTRIBUTION]) {
        nodes { createdAt }
      }
      lastFinOp: transactions(limit: 1) {
        nodes { createdAt kind type }
      }
      members(role: ADMIN, limit: 100) {
        totalCount
        nodes {
          account {
            name
            slug
            socialLinks { type url }
            ... on Individual {
              emails
              location { address country }
            }
          }
        }
      }
    }
  }
}
"""

PAGE_SIZE = 25


def first_node(collection: dict) -> dict:
    nodes = (collection or {}).get("nodes") or []
    return nodes[0] if nodes else {}


def extract_rows(collective: dict) -> list[dict]:
    """One row per (collective, admin)."""
    c_name = collective.get("name") or collective.get("slug") or ""
    c_slug = collective.get("slug") or ""
    c_url = f"https://opencollective.com/{c_slug}"
    if collective.get("isArchived"):
        c_name += " (archived)"

    # A None collection means the API nulled the field (e.g. token missing the
    # "transactions" scope) — that's "n/a", not "never".
    if collective.get("lastDonation") is None:
        last_donation = "n/a (token scope)"
    else:
        donation = first_node(collective.get("lastDonation"))
        last_donation = (donation.get("createdAt") or "")[:10] or "never"
    if collective.get("lastFinOp") is None:
        last_fin_op = "n/a (token scope)"
    else:
        fin_op = first_node(collective.get("lastFinOp"))
        last_fin_op = (fin_op.get("createdAt") or "")[:10]
        detail = " ".join(x for x in (fin_op.get("kind"), fin_op.get("type")) if x)
        if last_fin_op and detail:
            last_fin_op += f" ({detail})"
        last_fin_op = last_fin_op or "never"

    base = {
        "collective": c_name,
        "collective_url": c_url,
        "created": (collective.get("createdAt") or "")[:10],
        "last_donation": last_donation,
        "last_fin_op": last_fin_op,
    }

    rows = []
    members = (collective.get("members") or {}).get("nodes") or []
    for member in members:
        acc = member.get("account") or {}
        location = acc.get("location") or {}
        social = ", ".join(
            f"{(link.get('type') or '').lower()}: {link.get('url')}"
            for link in acc.get("socialLinks") or []
            if link.get("url")
        )
        rows.append(
            base
            | {
                "admin_name": acc.get("name") or "",
                "admin_url": f"https://opencollective.com/{acc.get('slug') or ''}",
                "all_emails": ", ".join(acc.get("emails") or []),
                "social": social,
                "address": (location.get("address") or "").replace("\n", ", "),
                "country": location.get("country") or "",
            }
        )
    if not members:
        rows.append(
            base
            | {
                "admin_name": "(no admins returned)",
                "admin_url": "",
                "all_emails": "",
                "social": "",
                "address": "",
                "country": "",
            }
        )
    admins_total = (collective.get("members") or {}).get("totalCount") or 0
    if admins_total > 100:
        print(f"note: {c_slug} has {admins_total} admins; only the first 100 exported", file=sys.stderr)
    return rows


COLUMNS = [
    ("collective", "Collective"),
    ("collective_url", "Collective URL"),
    ("created", "Created"),
    ("last_donation", "Last donation"),
    ("last_fin_op", "Last financial op"),
    ("admin_name", "Admin"),
    ("admin_url", "Admin profile"),
    ("all_emails", "Emails"),
    ("social", "Social media"),
    ("address", "Address"),
    ("country", "Country"),
]

# In Markdown output these text columns become clickable links to their URL
# column, and the raw-URL columns are dropped.
MD_LINKS = {"collective": "collective_url", "admin_name": "admin_url"}


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
    req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from Open Collective: {e.read().decode(errors='replace')}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error talking to Open Collective: {e.reason}")
    errors = payload.get("errors") or []
    # Scope-related Forbidden errors (e.g. a token without the "transactions"
    # scope) null out the affected fields but the rest of the data still comes
    # back — warn once per message and keep going instead of aborting.
    fatal = [e for e in errors if (e.get("extensions") or {}).get("code") != "Forbidden"]
    if fatal:
        sys.exit("GraphQL errors:\n" + json.dumps(fatal, indent=2))
    for msg in {e.get("message") for e in errors}:
        if msg not in _WARNED:
            _WARNED.add(msg)
            print(f"warning: {msg} — affected fields left empty "
                  f"(edit the token's scopes under Dashboard → For developers)", file=sys.stderr)
    return payload.get("data") or {}


def fetch_all(host_slug: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    total = None
    while total is None or offset < total:
        data = graphql(QUERY, {"host": [{"slug": host_slug}], "limit": PAGE_SIZE, "offset": offset})
        page = (data.get("accounts") or {})
        total = page.get("totalCount") or 0
        nodes = page.get("nodes") or []
        if not nodes:
            break
        for collective in nodes:
            rows.extend(extract_rows(collective))
        offset += len(nodes)
        print(f"fetched {min(offset, total)}/{total} collectives...", file=sys.stderr)
    rows.sort(key=lambda r: (r["collective"].lower(), r["admin_name"].lower()))
    return rows


def write_csv(rows: list[dict], out: str) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in COLUMNS])
        for r in rows:
            w.writerow([r.get(key, "") for key, _ in COLUMNS])


def write_md(rows: list[dict], out: str, title: str) -> None:
    url_cols = set(MD_LINKS.values())
    cols = [(key, label) for key, label in COLUMNS if key not in url_cols]
    labels = [label for _, label in cols]
    lines = [f"# {title}", "", "| " + " | ".join(labels) + " |", "| " + " | ".join(["---"] * len(labels)) + " |"]
    for r in rows:
        cells = []
        for key, _ in cols:
            text = str(r.get(key, "")).replace("|", "\\|")
            url = r.get(MD_LINKS.get(key, ""), "")
            cells.append(f"[{text}]({url})" if url and text else text)
        lines.append("| " + " | ".join(cells) + " |")
    collectives = len({r["collective_url"] for r in rows})
    lines += ["", f"_{len(rows)} row(s) across {collectives} collective(s)._", ""]
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
    pdf.set_font("Helvetica", "B", 8)
    for label in labels:
        pdf.cell(col_w, 8, label, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for r in rows:
        for key, _ in COLUMNS:
            text = str(r.get(key, ""))
            # latin-1 is fpdf's core-font encoding; drop anything outside it.
            pdf.cell(col_w, 7, text.encode("latin-1", "replace").decode("latin-1"), border=1)
        pdf.ln()
    pdf.output(out)


def run() -> None:
    ap = argparse.ArgumentParser(description="Export a host's collectives + admins (with personal data) to a local file.")
    ap.add_argument("--slug", default="europe", help="Host slug to query (default: europe).")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: reporting/output/<host-slug>-admins.<format>).")
    args = ap.parse_args()

    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        args.out = os.path.join(out_dir, f"{args.slug}-admins.{args.format}")

    if not (os.environ.get("OC_PERSONAL_TOKEN") or os.environ.get("OC_TOKEN")):
        print("warning: OC_PERSONAL_TOKEN not set — personal fields will be empty", file=sys.stderr)

    rows = fetch_all(args.slug)

    title = f"Collectives and admins — host '{args.slug}'"
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
