"""
IndexNow Cron Job — Automatically ping search engines for new Shazamme jobs.

Runs on a schedule, checks all sites for new jobs since last run,
and submits new job URLs to IndexNow + Google sitemap ping.

Usage:
    # Run once (checks for new jobs since last run)
    python indexnow_cron.py

    # Force re-index all jobs for all sites
    python indexnow_cron.py --full

    # Run for a specific site only
    python indexnow_cron.py --site 0ba2c165

    # Dry run (show what would be submitted)
    python indexnow_cron.py --dry-run

    # Write a per-site coverage report to public/audit.json + public/audit.html
    python indexnow_cron.py --report public

Set up as a cron job (every 15 minutes):
    */15 * * * * cd /path/to/dir && python3 indexnow_cron.py >> indexnow_cron.log 2>&1
"""

import argparse
import base64
import html
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SHAZAMME_API = "https://shazamme.io/Job-Listing/src/php/actions"
DUDA_API = "https://api.duda.co"
DUDA_USER = os.environ.get("DUDA_API_USER", "")
DUDA_PASS = os.environ.get("DUDA_API_PASS", "")
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "")
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".indexnow_state.json")


# ---------------------------------------------------------------------------
# State management — track which jobs we've already submitted
# ---------------------------------------------------------------------------


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"submitted_urls": {}, "last_run": None}


def save_state(state: dict) -> None:
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Duda API — get published sites
# ---------------------------------------------------------------------------


def get_published_sites() -> list[dict]:
    auth = "Basic " + base64.b64encode(f"{DUDA_USER}:{DUDA_PASS}".encode()).decode()
    sites = []
    offset = 0
    limit = 100

    while True:
        resp = requests.get(
            f"{DUDA_API}/api/sites/multiscreen",
            headers={"Authorization": auth},
            params={"offset": offset, "limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        sites.extend(results)

        if len(results) < limit:
            break
        offset += limit
        time.sleep(0.2)

    return [s for s in sites if s.get("publish_status") == "PUBLISHED"]


# ---------------------------------------------------------------------------
# Duda API — get site pages
# ---------------------------------------------------------------------------


def get_site_pages(site_name: str, domain: str) -> list[str]:
    """Get all page URLs for a Duda site."""
    auth = "Basic " + base64.b64encode(f"{DUDA_USER}:{DUDA_PASS}".encode()).decode()
    try:
        resp = requests.get(
            f"{DUDA_API}/api/sites/multiscreen/site/{site_name}/pages",
            headers={"Authorization": auth},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        pages = resp.json()
        urls = []
        for page in pages:
            path = page.get("page_path", "")
            if path and not page.get("seo", {}).get("no_index", False):
                url = f"https://{domain}/{path}" if path != "home" else f"https://{domain}/"
                urls.append(url)
        return urls
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Shazamme API — get jobs for a site
# ---------------------------------------------------------------------------


def get_jobs(duda_site_id: str) -> list[dict]:
    try:
        resp = requests.get(
            SHAZAMME_API,
            params={"dudaSiteID": duda_site_id, "action": "Get Jobs"},
            timeout=60,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# IndexNow submission
# ---------------------------------------------------------------------------


def submit_to_indexnow(urls: list[str], domain: str) -> bool:
    if not urls:
        return True

    try:
        resp = requests.post(
            INDEXNOW_ENDPOINT,
            json={
                "host": domain,
                "key": INDEXNOW_KEY,
                "keyLocation": f"https://{domain}/{INDEXNOW_KEY}.txt",
                "urlList": urls[:10000],
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        return resp.status_code in (200, 202)
    except Exception:
        return False






# ---------------------------------------------------------------------------
# Main cron logic
# ---------------------------------------------------------------------------


def write_audit(report_dir: str, audit: list, summary: dict) -> None:
    os.makedirs(report_dir, exist_ok=True)
    json_path = os.path.join(report_dir, "audit.json")
    with open(json_path, "w") as f:
        json.dump({"summary": summary, "sites": audit}, f, indent=2)

    audit_sorted = sorted(audit, key=lambda r: (r["missing"], -r["total"]), reverse=True)
    rows = "\n".join(
        f'      <tr><td>{html.escape(r["domain"] or r["site_id"])}</td>'
        f'<td>{r["total"]}</td><td>{r["submitted"]}</td>'
        f'<td class="{"miss" if r["missing"] else "ok"}">{r["missing"]}</td>'
        f'<td>{r["coverage"]:.0%}</td></tr>'
        for r in audit_sorted
    )
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>IndexNow Coverage Audit</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:.45em;text-align:left}}
.ok{{color:#0a7}}.miss{{color:#c33;font-weight:600}}
.kpi{{display:flex;gap:2em;margin:1.5em 0}}
.kpi div{{padding:.5em 1em;background:#f4f4f4;border-radius:6px}}
.kpi b{{display:block;font-size:1.5em}}</style></head><body>
<h1>IndexNow Coverage Audit</h1>
<p>Last run: <code>{html.escape(summary["last_run"])}</code></p>
<div class="kpi">
  <div><b>{summary["total_sites"]}</b>sites</div>
  <div><b>{summary["total_urls"]:,}</b>URLs known</div>
  <div><b>{summary["submitted_urls"]:,}</b>submitted</div>
  <div><b>{summary["missing_urls"]:,}</b>missing</div>
  <div><b>{summary["overall_coverage"]:.1%}</b>coverage</div>
</div>
<table><thead><tr><th>Domain</th><th>Known URLs</th><th>Submitted</th><th>Missing</th><th>Coverage</th></tr></thead>
<tbody>
{rows}
</tbody></table>
<p style="margin-top:2em;color:#666"><small>Coverage = (submitted ÷ known). 100% means every page + job URL has been pushed to IndexNow at least once. Source of truth for indexing status is <a href="https://www.bing.com/webmasters">Bing Webmaster Tools</a>.</small></p>
</body></html>
"""
    with open(os.path.join(report_dir, "audit.html"), "w") as f:
        f.write(page)
    print(f"Audit written: {json_path} + audit.html")


def run(dry_run: bool = False, full: bool = False, site_filter: str = None, report_dir: str = None):
    now = datetime.now(timezone.utc).isoformat()
    state = load_state()
    submitted = state.get("submitted_urls", {})

    if full:
        submitted = {}

    print(f"[{now}] IndexNow cron starting...")
    print(f"Last run: {state.get('last_run', 'never')}")

    # Get all published sites
    if site_filter:
        sites = [{"site_name": site_filter}]
        print(f"Running for single site: {site_filter}")
    else:
        print("Fetching published sites...")
        sites = get_published_sites()
        print(f"Found {len(sites)} published sites")

    total_new = 0
    total_submitted = 0
    sites_with_new_content = 0
    audit = []

    for i, site in enumerate(sites, 1):
        site_name = site["site_name"]
        domain = site.get("site_domain", site.get("site_default_domain", ""))
        if not domain:
            continue

        page_urls = get_site_pages(site_name, domain)
        jobs = get_jobs(site_name)
        job_urls = [
            (j.get("data", j).get("jobURL"))
            for j in jobs
            if j.get("data", j).get("jobURL")
        ]

        all_urls = set(page_urls) | set(job_urls)
        new_urls = [u for u in all_urls if u not in submitted]

        if new_urls:
            total_new += len(new_urls)
            sites_with_new_content += 1
            job_count = sum(1 for u in new_urls if "/job-details/" in u)
            page_count = len(new_urls) - job_count
            print(f"  [{i}/{len(sites)}] {site_name} ({domain}): {page_count} pages, {job_count} jobs")

            if dry_run:
                for url in new_urls[:5]:
                    print(f"    WOULD SUBMIT: {url}")
                if len(new_urls) > 5:
                    print(f"    ... and {len(new_urls) - 5} more")
            else:
                success = submit_to_indexnow(new_urls, domain)
                if success:
                    total_submitted += len(new_urls)
                    for url in new_urls:
                        submitted[url] = now
                    print(f"    IndexNow: OK ({len(new_urls)} URLs)")
                else:
                    print(f"    IndexNow: FAILED")
                time.sleep(0.5)

        if report_dir and all_urls:
            sub_count = sum(1 for u in all_urls if u in submitted)
            audit.append({
                "site_id": site_name,
                "domain": domain,
                "pages": len(page_urls),
                "jobs": len(job_urls),
                "total": len(all_urls),
                "submitted": sub_count,
                "missing": len(all_urls) - sub_count,
                "coverage": sub_count / len(all_urls) if all_urls else 1.0,
            })

    # Save state
    if not dry_run:
        state["submitted_urls"] = submitted
        save_state(state)

    print(f"\n{'DRY RUN ' if dry_run else ''}Summary:")
    print(f"  Sites with new content: {sites_with_new_content}")
    print(f"  New URLs found: {total_new}")
    print(f"  URLs submitted: {total_submitted if not dry_run else 'N/A (dry run)'}")
    print(f"  Total URLs tracked: {len(submitted)}")

    if report_dir and audit:
        total_urls = sum(r["total"] for r in audit)
        submitted_urls = sum(r["submitted"] for r in audit)
        summary = {
            "last_run": now,
            "total_sites": len(audit),
            "total_urls": total_urls,
            "submitted_urls": submitted_urls,
            "missing_urls": total_urls - submitted_urls,
            "overall_coverage": submitted_urls / total_urls if total_urls else 1.0,
        }
        write_audit(report_dir, audit, summary)


def main():
    parser = argparse.ArgumentParser(description="IndexNow cron job for Shazamme jobs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without submitting")
    parser.add_argument("--full", action="store_true", help="Re-index all jobs (ignore state)")
    parser.add_argument("--site", type=str, help="Run for a specific Duda site ID only")
    parser.add_argument("--report", type=str, help="Write audit.json + audit.html to this directory")
    args = parser.parse_args()

    run(dry_run=args.dry_run, full=args.full, site_filter=args.site, report_dir=args.report)


if __name__ == "__main__":
    main()
