# NSE OI Spurts Dashboard

A Streamlit app that fetches live "OI Spurts" data from NSE India
(https://www.nseindia.com/market-data/oi-spurts) and shows which symbol
has the top % change in Open Interest, with a chart of the top 10 movers.

## Files
- `app.py` — the Streamlit app
- `nse_oi_spurts.py` — plain command-line version (no Streamlit)
- `requirements.txt` — Python dependencies

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Then open the local URL Streamlit prints (usually http://localhost:8501).

## Push to GitHub
```bash
git init
git add app.py requirements.txt README.md nse_oi_spurts.py
git commit -m "NSE OI Spurts Streamlit app"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## Deploy on Streamlit Community Cloud
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click "New app".
3. Select your repo, branch (`main`), and set the main file path to `app.py`.
4. Click "Deploy".

## ⚠️ Important limitation: NSE blocks cloud IPs
NSE India's servers frequently block requests coming from datacenter /
cloud IP ranges — which is exactly what Streamlit Cloud, GitHub Actions,
Heroku, Render, etc. all use. Practically, this means:

- **Locally (your home Wi-Fi):** usually works fine.
- **Deployed on Streamlit Cloud:** may get blocked (403 or empty response).
  The app is built to fail gracefully and show a clear message instead of
  crashing, but it may not reliably return live data once deployed.

The app now has two built-in mitigations:
1. **Longer timeout + exponential backoff** (30s timeout, 4 retries) —
   handles cases where NSE is just slow rather than fully blocking.
2. **`nsepython` fallback** — if the direct `requests` approach fails,
   the app automatically tries `nsepython`, a community library built
   specifically to survive NSE's cookie/anti-bot checks. It's not
   guaranteed to work from every cloud IP either, but it's noticeably
   more reliable than plain `requests` in practice.

### If it's still blocked after both attempts
- **Residential proxy (most reliable fix):** sign up for a scraping
  proxy service (e.g. ScraperAPI, Bright Data, Smartproxy). Add the
  proxy URL to Streamlit Cloud's app secrets as:
  ```toml
  PROXY_URL = "http://user:pass@proxy-host:port"
  ```
  The app already reads this automatically (`_get_proxies()` in
  `app.py`) and routes requests through it.
- **Fetch locally, serve from the cloud:** run `nse_oi_spurts.py` on
  your own machine on a schedule (cron / Task Scheduler), have it write
  to a CSV or small database (e.g. a free Postgres on Supabase/Neon),
  and point the Streamlit Cloud app at that instead of calling NSE
  directly.
- **Self-host:** run the Streamlit app on a home server or a VPS with a
  residential-like IP instead of Streamlit Community Cloud.

## Note on NSE's JSON field names
NSE occasionally changes the exact field names in their API responses.
If the "% change in OI" column doesn't populate, the app will show you
the raw column names it received — update the `CANDIDATES` dictionary
near the top of `app.py` (or `normalize_columns()` in `nse_oi_spurts.py`)
to match.
