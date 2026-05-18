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

Set up as a cron job (every 15 minutes):
    */15 * * * * cd /path/to/dir && python3 indexnow_cron.py >> indexnow_cron.log 2>&1
"""

import argparse
import base64
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


def run(dry_run: bool = False, full: bool = False, site_filter: str = None):
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

    for i, site in enumerate(sites, 1):
        site_name = site["site_name"]
        domain = site.get("site_domain", site.get("site_default_domain", ""))
        if not domain:
            continue

        new_urls = []

        # Get site pages
        page_urls = get_site_pages(site_name, domain)
        for url in page_urls:
            if url not in submitted:
                new_urls.append(url)

        # Get jobs for this site
        jobs = get_jobs(site_name)
        for job in jobs:
            job_data = job.get("data", job)
            url = job_data.get("jobURL")
            if url and url not in submitted:
                new_urls.append(url)

        if not new_urls:
            continue

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
            continue

        # Submit to IndexNow
        success = submit_to_indexnow(new_urls, domain)
        if success:
            total_submitted += len(new_urls)
            for url in new_urls:
                submitted[url] = now
            print(f"    IndexNow: OK ({len(new_urls)} URLs)")
        else:
            print(f"    IndexNow: FAILED")

        # Rate limit between sites
        time.sleep(0.5)

    # Save state
    if not dry_run:
        state["submitted_urls"] = submitted
        save_state(state)

    print(f"\n{'DRY RUN ' if dry_run else ''}Summary:")
    print(f"  Sites with new content: {sites_with_new_content}")
    print(f"  New URLs found: {total_new}")
    print(f"  URLs submitted: {total_submitted if not dry_run else 'N/A (dry run)'}")
    print(f"  Total URLs tracked: {len(submitted)}")


def main():
    parser = argparse.ArgumentParser(description="IndexNow cron job for Shazamme jobs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without submitting")
    parser.add_argument("--full", action="store_true", help="Re-index all jobs (ignore state)")
    parser.add_argument("--site", type=str, help="Run for a specific Duda site ID only")
    args = parser.parse_args()

    run(dry_run=args.dry_run, full=args.full, site_filter=args.site)


if __name__ == "__main__":
    main()
