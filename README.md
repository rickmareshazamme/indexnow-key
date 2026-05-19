# indexnow-key

Automated IndexNow submission for all published Shazamme job sites. Pings Bing, Yandex, and other IndexNow-compatible search engines whenever new jobs or pages appear, so listings get indexed within minutes instead of days.

## What it does

A GitHub Actions cron runs every 15 minutes and:

1. Fetches every **PUBLISHED** site from the Duda API.
2. For each site, pulls its pages (skipping `no_index`) and its jobs (via the Shazamme `Get Jobs` action).
3. Diffs against `.indexnow_state.json` to find URLs that haven't been submitted before.
4. POSTs the new URLs to `https://api.indexnow.org/indexnow` with the host's key.
5. Persists the updated state back to the Actions cache so the next run only submits genuinely new URLs.

The IndexNow key (`9ed162af85e84f97b22234647c7bd399`) is verified by serving `9ed162af85e84f97b22234647c7bd399.txt` from the root of each Shazamme site.

## Files

- [indexnow_cron.py](indexnow_cron.py) — the cron script.
- [.github/workflows/index-jobs.yml](.github/workflows/index-jobs.yml) — runs the script every 15 minutes (cron `7,22,37,52 * * * *`) and on manual dispatch.
- [9ed162af85e84f97b22234647c7bd399.txt](9ed162af85e84f97b22234647c7bd399.txt) — IndexNow key verification file.

## Required secrets

Configured under **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|---|---|
| `INDEXNOW_KEY` | The IndexNow key (matches the `.txt` filename). |
| `DUDA_API_USER` | Duda API username for listing sites/pages. |
| `DUDA_API_PASS` | Duda API password. |

## Running locally

```bash
pip install requests

export INDEXNOW_KEY=9ed162af85e84f97b22234647c7bd399
export DUDA_API_USER=...
export DUDA_API_PASS=...

# Submit only new URLs (default)
python indexnow_cron.py

# Preview without submitting
python indexnow_cron.py --dry-run

# Re-submit everything, ignoring state
python indexnow_cron.py --full

# Single site
python indexnow_cron.py --site <duda_site_id>
```

State is stored in `.indexnow_state.json` next to the script.

## Manual trigger

```bash
gh workflow run index-jobs.yml -R rickmareshazamme/indexnow-key
```
