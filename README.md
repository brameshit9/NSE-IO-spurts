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

### Workarounds if you hit blocking on deployment
- Use a scraping proxy service (e.g. ScraperAPI, Bright Data) that routes
  requests through residential IPs — swap the `requests.Session()` calls
  in `app.py` to go through the proxy.
- Run the fetch on a schedule from your own machine (e.g. a cron job) and
  have it write results to a small database or CSV that the Streamlit
  Cloud app reads instead of hitting NSE directly.
- Self-host the Streamlit app (e.g. on a home server or a VPS with a
  residential-like IP) rather than using Streamlit Community Cloud.

## Note on NSE's JSON field names
NSE occasionally changes the exact field names in their API responses.
If the "% change in OI" column doesn't populate, the app will show you
the raw column names it received — update the `CANDIDATES` dictionary
near the top of `app.py` (or `normalize_columns()` in `nse_oi_spurts.py`)
to match.
