"""
Generate XML job feeds for each Shazamme site.

Produces an Indeed/HR-XML compatible feed per Duda site (accepted by CareerJet,
Jooble, Talent.com, PostJobFree, ZipRecruiter, Monster, and most aggregators).

Outputs:
    feeds/<duda_site_id>.xml   — per-site feed
    feeds/feeds.txt            — newline-delimited list of every feed URL
    feeds/index.html           — human-readable index of every feed URL

Usage:
    python generate_feeds.py                 # all sites
    python generate_feeds.py --site <id>     # single site
    python generate_feeds.py --out feeds     # custom output dir
"""
from __future__ import annotations

import argparse
import base64
import html
import os
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

import requests

DUDA_API = "https://api.duda.co"
SHAZAMME_API = "https://shazamme.io/Job-Listing/src/php/actions"
DUDA_USER = os.environ.get("DUDA_API_USER", "")
DUDA_PASS = os.environ.get("DUDA_API_PASS", "")

PUBLISHER_NAME = "Shazamme"
PUBLISHER_URL = "https://shazamme.com"


def duda_auth_header() -> dict:
    token = base64.b64encode(f"{DUDA_USER}:{DUDA_PASS}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def get_published_sites() -> list[dict]:
    sites = []
    offset = 0
    limit = 100
    while True:
        resp = requests.get(
            f"{DUDA_API}/api/sites/multiscreen",
            headers=duda_auth_header(),
            params={"offset": offset, "limit": limit},
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        sites.extend(results)
        if len(results) < limit:
            break
        offset += limit
        time.sleep(0.2)
    return [s for s in sites if s.get("publish_status") == "PUBLISHED"]


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
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"    get_jobs failed for {duda_site_id}: {e}")
        return []


def cdata(value) -> str:
    if value is None:
        return "<![CDATA[]]>"
    text = str(value).replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{text}]]>"


def map_work_type(job_type: str | None, work_type: str | None) -> str:
    raw = " ".join(filter(None, [job_type, work_type])).lower()
    if "part" in raw:
        return "parttime"
    if "contract" in raw or "temp" in raw:
        return "contract"
    if "intern" in raw:
        return "internship"
    if "casual" in raw:
        return "parttime"
    return "fulltime"


def map_remote(work_model: str | None) -> str:
    if not work_model:
        return ""
    raw = work_model.lower()
    if "remote" in raw:
        return "telecommute"
    if "hybrid" in raw:
        return "hybrid"
    return "onsite"


def format_salary(job: dict) -> str:
    text = job.get("salaryText") or job.get("salary")
    if text:
        return str(text)
    lo = job.get("realSalaryFrom") or job.get("salaryFrom")
    hi = job.get("realSalaryTo") or job.get("salaryTo")
    sym = job.get("currencySymbol") or ""
    period = job.get("salaryType") or ""
    if lo and hi:
        return f"{sym}{lo} - {sym}{hi} {period}".strip()
    if lo:
        return f"{sym}{lo} {period}".strip()
    return ""


def parse_posted_date(job: dict) -> str:
    raw = job.get("addedOnUTC") or job.get("postedDate") or ""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            dt = datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
            return format_datetime(dt)
        except (ValueError, TypeError):
            continue
    return format_datetime(datetime.now(timezone.utc))


def job_to_xml(job_record: dict, site_domain: str) -> str:
    d = job_record.get("data", job_record)
    url = d.get("jobURL") or ""
    if not url and site_domain and job_record.get("page_item_url"):
        url = f"https://{site_domain}/job-details/{job_record['page_item_url']}"
    if not url:
        return ""

    parts = [
        "  <job>",
        f"    <title>{cdata(d.get('jobName') or d.get('positionTitle'))}</title>",
        f"    <date>{cdata(parse_posted_date(d))}</date>",
        f"    <referencenumber>{cdata(d.get('referenceNumber') or d.get('jobID'))}</referencenumber>",
        f"    <url>{cdata(url)}</url>",
        f"    <company>{cdata(d.get('advertiserName'))}</company>",
        f"    <sourcename>{cdata(PUBLISHER_NAME)}</sourcename>",
        f"    <city>{cdata(d.get('city'))}</city>",
        f"    <state>{cdata(d.get('state'))}</state>",
        f"    <country>{cdata(d.get('country'))}</country>",
        f"    <postalcode>{cdata(d.get('postalCode'))}</postalcode>",
        f"    <description>{cdata(d.get('fullDescription') or d.get('shortDescription'))}</description>",
        f"    <salary>{cdata(format_salary(d))}</salary>",
        f"    <category>{cdata(d.get('category'))}</category>",
        f"    <jobtype>{cdata(map_work_type(d.get('jobType'), d.get('workType')))}</jobtype>",
    ]
    remote = map_remote(d.get("workModel"))
    if remote:
        parts.append(f"    <remotetype>{cdata(remote)}</remotetype>")
    lat, lon = d.get("latitude"), d.get("longitude")
    if lat and lon:
        parts.append(f"    <latitude>{cdata(lat)}</latitude>")
        parts.append(f"    <longitude>{cdata(lon)}</longitude>")
    parts.append("  </job>")
    return "\n".join(parts)


def write_feed(path: str, jobs_xml: list[str]) -> None:
    now = format_datetime(datetime.now(timezone.utc))
    body = "\n".join(jobs_xml)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<source>\n"
        f"  <publisher>{escape(PUBLISHER_NAME)}</publisher>\n"
        f"  <publisherurl>{escape(PUBLISHER_URL)}</publisherurl>\n"
        f"  <lastBuildDate>{escape(now)}</lastBuildDate>\n"
        f"{body}\n"
        "</source>\n"
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(xml)


def write_index(path: str, entries: list[dict], base_url: str) -> None:
    rows = "\n".join(
        f'      <tr><td>{html.escape(e["name"])}</td>'
        f'<td>{html.escape(e["domain"])}</td>'
        f'<td>{e["jobs"]}</td>'
        f'<td><a href="{html.escape(e["site_id"])}.xml">{html.escape(e["site_id"])}.xml</a></td></tr>'
        for e in entries
    )
    total_jobs = sum(e["jobs"] for e in entries)
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Shazamme Job Feeds</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:.5em;text-align:left}}
code{{background:#f4f4f4;padding:.1em .3em;border-radius:3px}}</style>
</head><body>
<h1>Shazamme Job Feeds</h1>
<p>Indeed/HR-XML compatible feeds for {len(entries)} live sites, {total_jobs:,} total jobs. Updated every 15 minutes.</p>
<p>All feed URLs (one per line): <a href="feeds.txt">feeds.txt</a> &middot; IndexNow coverage report: <a href="audit.html">audit.html</a></p>
<table><thead><tr><th>Site</th><th>Domain</th><th>Jobs</th><th>Feed</th></tr></thead>
<tbody>
{rows}
</tbody></table>
</body></html>
"""
    with open(path, "w") as f:
        f.write(page)


def write_feed_list(path: str, entries: list[dict], base_url: str) -> None:
    with open(path, "w") as f:
        for e in entries:
            f.write(f"{base_url.rstrip('/')}/{e['site_id']}.xml\n")


def run(out_dir: str, site_filter: str | None = None, base_url: str = "") -> None:
    os.makedirs(out_dir, exist_ok=True)

    if site_filter:
        sites = [{"site_name": site_filter, "site_domain": ""}]
    else:
        print("Fetching published sites...")
        sites = get_published_sites()
        print(f"Found {len(sites)} published sites")

    entries = []
    total_jobs = 0

    for i, site in enumerate(sites, 1):
        site_id = site["site_name"]
        domain = site.get("site_domain") or site.get("site_default_domain") or ""
        jobs = get_jobs(site_id)
        if not jobs:
            print(f"  [{i}/{len(sites)}] {site_id}: no jobs, skipping")
            continue

        jobs_xml = [x for x in (job_to_xml(j, domain) for j in jobs) if x]
        if not jobs_xml:
            continue

        feed_path = os.path.join(out_dir, f"{site_id}.xml")
        write_feed(feed_path, jobs_xml)
        total_jobs += len(jobs_xml)
        entries.append({
            "site_id": site_id,
            "name": site.get("site_business_info", {}).get("business_name") or domain or site_id,
            "domain": domain,
            "jobs": len(jobs_xml),
        })
        print(f"  [{i}/{len(sites)}] {site_id} ({domain}): {len(jobs_xml)} jobs")
        time.sleep(0.2)

    if entries and not site_filter:
        write_index(os.path.join(out_dir, "index.html"), entries, base_url)
        write_feed_list(os.path.join(out_dir, "feeds.txt"), entries, base_url)

    print(f"\nGenerated {len(entries)} feeds, {total_jobs} total jobs → {out_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Generate XML job feeds")
    parser.add_argument("--out", default="feeds", help="Output directory (default: feeds)")
    parser.add_argument("--site", help="Single Duda site ID")
    parser.add_argument(
        "--base-url",
        default="https://rickmareshazamme.github.io/indexnow-key",
        help="Public URL where feeds will be served (used in feeds.txt)",
    )
    args = parser.parse_args()
    run(args.out, args.site, args.base_url)


if __name__ == "__main__":
    main()
