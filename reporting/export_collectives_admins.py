# /// script
# requires-python = ">=3.10"
# dependencies = ["fpdf2>=2.7"]
# ///
"""Export the admins (+ emails, country, social links) of a chosen list of
Open Collective collectives — run by YOU, never by the AI.

Python rewrite of the old oc-admins.mjs. The data flows Open Collective API
-> your disk; it never passes through an AI context.

Usage, from inside the reporting/ directory (uv fetches the deps automatically
from the header above):

    export OC_PERSONAL_TOKEN='<your token — Dashboard → For developers>'
    uv run export_collectives_admins.py                    # baked-in slug list
    uv run export_collectives_admins.py manjaro keycloak   # explicit slugs
    uv run export_collectives_admins.py --format csv

Emails and country are private: the API only returns them to the account owner
or an authorized host admin; for everyone else they come back empty. Output
defaults to the gitignored output/ folder next to this script.
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
_WARNED: set[str] = set()

# Default list: the top collectives from the "europe" host, as in oc-admins.mjs.
# Override by passing slugs on the command line.
DEFAULT_SLUGS = [
    "techworkersber", "monnaie-libre", "postmarketos", "edgetx",
    "omstallningsvanner", "interbeing", "gpxstudio", "microcosm",
    "rotorflight", "fedimon", "alversjo", "f-droid-euro", "bazzite-eu",
    "endeavouros", "techworkersco", "courtbouillon", "manjaro", "keycloak",
    "gotosocial", "lambda-island", "xfce-eu", "nix-community",
    "yellowbrick-cycling", "devstaff", "the-rockstor-project",
    "projectliminality", "kamailio", "enspiral-europe", "flightgear",
    "kollektiv-email", "reactive-resume", "mastodonworld",
]

QUERY = """
query ($slug: String!) {
  account(slug: $slug) {
    slug
    name
    members(role: ADMIN, limit: 100) {
      nodes {
        account {
          slug
          name
          socialLinks { type url }
          location { country }
          ... on Individual { emails }
        }
      }
    }
  }
}
"""


def extract_rows(account: dict) -> list[dict]:
    """One row per admin of one collective."""
    rows = []
    for member in (account.get("members") or {}).get("nodes") or []:
        acc = member.get("account") or {}
        social = " | ".join(
            f"{(link.get('type') or '').lower()}:{link.get('url')}"
            for link in acc.get("socialLinks") or []
            if link.get("url")
        )
        rows.append(
            {
                "collective": account.get("name") or "",
                "collective_url": f"https://opencollective.com/{account.get('slug') or ''}",
                "admin_name": acc.get("name") or "",
                "admin_url": f"https://opencollective.com/{acc.get('slug') or ''}",
                "all_emails": ", ".join(acc.get("emails") or []),
                "social": social,
                "country": (acc.get("location") or {}).get("country") or "",
            }
        )
    return rows


COLUMNS = [
    ("collective", "Collective"),
    ("collective_url", "Collective URL"),
    ("admin_name", "Admin"),
    ("admin_url", "Admin profile"),
    ("all_emails", "Emails"),
    ("social", "Social media"),
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
    # Scope-related Forbidden errors null out the affected fields but the rest
    # of the data still comes back — warn once per message and keep going.
    fatal = [e for e in errors if (e.get("extensions") or {}).get("code") != "Forbidden"]
    if fatal:
        sys.exit("GraphQL errors:\n" + json.dumps(fatal, indent=2))
    for msg in {e.get("message") for e in errors}:
        if msg not in _WARNED:
            _WARNED.add(msg)
            print(f"warning: {msg} — affected fields left empty "
                  f"(edit the token's scopes under Dashboard → For developers)", file=sys.stderr)
    return payload.get("data") or {}


def fetch_all(slugs: list[str]) -> list[dict]:
    rows: list[dict] = []
    for i, slug in enumerate(slugs):
        data = graphql(QUERY, {"slug": slug})
        account = data.get("account")
        if not account:
            print(f"warning: collective '{slug}' not found — skipped", file=sys.stderr)
            continue
        found = extract_rows(account)
        rows.extend(found)
        print(f"fetched {slug}: {len(found)} admin(s) ({i + 1}/{len(slugs)})", file=sys.stderr)
        time.sleep(0.3)  # be polite to the API
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
    ap = argparse.ArgumentParser(description="Export admins of selected collectives (with personal data) to a local file.")
    ap.add_argument("slugs", nargs="*", default=None,
                    help=f"Collective slugs to query (default: baked-in list of {len(DEFAULT_SLUGS)}).")
    ap.add_argument("--format", choices=["csv", "md", "pdf"], default="md")
    ap.add_argument("--out", default=None,
                    help="Output file path (default: output/collectives-admins.<format> next to this script).")
    args = ap.parse_args()

    if not args.out:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        args.out = os.path.join(out_dir, f"collectives-admins.{args.format}")

    if not (os.environ.get("OC_PERSONAL_TOKEN") or os.environ.get("OC_TOKEN")):
        print("warning: OC_PERSONAL_TOKEN not set — personal fields will be empty", file=sys.stderr)

    rows = fetch_all(args.slugs or DEFAULT_SLUGS)

    title = "Admins — selected collectives"
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
