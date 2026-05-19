# indexnow-key

Automated job distribution for all published Shazamme sites. Two things run on a 15-minute cron:

1. **IndexNow ping** — submits new job/page URLs to Bing, Yandex, etc.
2. **XML job feeds** — generates an Indeed/HR-XML compatible feed per site and publishes them to GitHub Pages for commercial job boards (CareerJet, Jooble, Talent.com, PostJobFree, ZipRecruiter, Monster, etc.) to crawl.

## What it does

Every 15 minutes the GitHub Actions workflow:

1. Lists every **PUBLISHED** site from the Duda API.
2. **IndexNow job** — pulls each site's pages + Shazamme jobs, diffs against `.indexnow_state.json`, POSTs new URLs to `https://api.indexnow.org/indexnow`.
3. **Feeds job** — generates `<duda_site_id>.xml` per site plus a combined `all.xml`, and pushes them to the `gh-pages` branch.

Published feed index: **https://rickmareshazamme.github.io/indexnow-key/**

Per-site feed URL pattern:
```
https://rickmareshazamme.github.io/indexnow-key/<duda_site_id>.xml
```

Combined feed (all sites, every live job):
```
https://rickmareshazamme.github.io/indexnow-key/all.xml
```

The IndexNow key (`9ed162af85e84f97b22234647c7bd399`) is verified by serving `9ed162af85e84f97b22234647c7bd399.txt` from each Shazamme site root.

## Job board registration

Once feeds are live, register the feed URL with each board (most are one-time forms — no per-job API).

| Board | Type | URL to register | Notes |
|---|---|---|---|
| CareerJet | Free XML feed | partners.careerjet.com | Submit `all.xml` or per-site |
| Jooble | Free XML feed | jooble.org/jobs-partners | Free organic feed |
| Talent.com (Neuvoo) | Free + paid | talent.com/partner | Free organic, paid CPC available |
| PostJobFree | Free XML feed | postjobfree.com/free-job-posting | Submit feed URL |
| MyJobHelper | Aggregator | partners.myjobhelper.com | Picks up via XML |
| StartWire | Aggregator | Mostly scraped via Indeed/Recruitics | Usually no direct submission |
| Indeed | **Paid only since 2024** | employers.indeed.com | Free organic XML deprecated |
| Monster | Paid posting API | partner.monster.com | Job posting API, paid |
| ZipRecruiter | Paid / partnership | ziprecruiter.com/partner | Mostly sponsored |
| Neuvoo | = Talent.com | (same as Talent.com) | Same company |
| JobFuel | Aggregator | jobfuel.com | Receives via Recruitics |
| Job Swipe | Aggregator | jobswipe.com | Scrapes |
| Zippia | Aggregator | Bought by ZipRecruiter 2024 | Via ZipRecruiter feed |
| Recruitics | Programmatic ad platform | recruitics.com | Paid, distributes to many boards |
| Talent Inc. | Programmatic | talentinc.com | Paid |

**LinkedIn**: no free programmatic posting since 2023. Options are manual posting via Company Page (1 free job at a time), Promoted Jobs (PPC), or Recruiter System Connect (paid Recruiter seat required). Free play: ensure each job-details page has correct JobPosting JSON-LD schema — LinkedIn People Search picks those up.

## Files

- [indexnow_cron.py](indexnow_cron.py) — IndexNow submission script.
- [generate_feeds.py](generate_feeds.py) — XML feed generator.
- [.github/workflows/index-jobs.yml](.github/workflows/index-jobs.yml) — runs both every 15 min.
- [9ed162af85e84f97b22234647c7bd399.txt](9ed162af85e84f97b22234647c7bd399.txt) — IndexNow key verification.

## Required secrets

**Settings → Secrets and variables → Actions**:

| Secret | Used by |
|---|---|
| `INDEXNOW_KEY` | IndexNow cron |
| `DUDA_API_USER` | Both jobs (to list sites) |
| `DUDA_API_PASS` | Both jobs |

## Required repo setting

GitHub Pages must be enabled from the `gh-pages` branch (Settings → Pages → Source: `gh-pages` / `/`). The first workflow run creates the branch; enable Pages after that.

## Running locally

```bash
pip install requests
export INDEXNOW_KEY=9ed162af85e84f97b22234647c7bd399
export DUDA_API_USER=...
export DUDA_API_PASS=...

# IndexNow
python indexnow_cron.py --dry-run     # preview
python indexnow_cron.py                # submit new URLs
python indexnow_cron.py --full         # re-submit everything
python indexnow_cron.py --site <id>    # one site only

# Feeds
python generate_feeds.py               # writes to feeds/
python generate_feeds.py --out public  # custom dir
python generate_feeds.py --site <id>   # one site only
```

## Manual trigger

```bash
gh workflow run index-jobs.yml -R rickmareshazamme/indexnow-key
```

## Feed format

Indeed/HR-XML standard — accepted by virtually every aggregator:

```xml
<?xml version="1.0" encoding="utf-8"?>
<source>
  <publisher>Shazamme</publisher>
  <publisherurl>https://shazamme.com</publisherurl>
  <lastBuildDate>...</lastBuildDate>
  <job>
    <title><![CDATA[Financial Accountant]]></title>
    <date><![CDATA[Mon, 18 May 2026 09:30:00 GMT]]></date>
    <referencenumber><![CDATA[187205]]></referencenumber>
    <url><![CDATA[https://...]]></url>
    <company><![CDATA[...]]></company>
    <city><![CDATA[Sydney]]></city>
    <state><![CDATA[NSW]]></state>
    <country><![CDATA[Australia]]></country>
    <postalcode><![CDATA[2000]]></postalcode>
    <description><![CDATA[<p>...HTML allowed...</p>]]></description>
    <salary><![CDATA[$65-75 per hour]]></salary>
    <category><![CDATA[Accounting]]></category>
    <jobtype><![CDATA[contract]]></jobtype>
    <remotetype><![CDATA[onsite]]></remotetype>
  </job>
</source>
```
