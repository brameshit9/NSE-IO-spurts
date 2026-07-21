"""
NSE "OI Spurts" - Streamlit App
--------------------------------
Source page : https://www.nseindia.com/market-data/oi-spurts
API used    : https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Deploy on Streamlit Community Cloud:
    1. Push this repo to GitHub (app.py + requirements.txt).
    2. Go to https://share.streamlit.io -> "New app" -> pick your repo/branch
       -> set main file path to "app.py" -> Deploy.

IMPORTANT: NSE aggressively blocks requests coming from datacenter/cloud
IPs (which is what Streamlit Cloud, GitHub Actions, Heroku, etc. use).
It often works fine locally on a home connection but gets blocked (403 /
empty response) once deployed. If that happens here, the app will show
a clear error message rather than crashing.
"""

import time
import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

BASE_URL = "https://www.nseindia.com"
HOME_URL = f"{BASE_URL}/market-data/oi-spurts"
API_URL = f"{BASE_URL}/api/live-analysis-oi-spurts-underlyings"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": HOME_URL,
    "X-Requested-With": "XMLHttpRequest",
}

CANDIDATES = {
    "symbol": ["symbol", "underlying", "Symbol"],
    "instrument": ["instrument", "instrumentType", "Instrument"],
    "expiry": ["expiryDate", "optExpiryDt", "expiry_dt", "Expiry"],
    "oi_current": ["latestOI", "openInterest", "currOI", "oi", "OI_current"],
    "oi_previous": ["prevOI", "previousOI", "oiPrevious", "OI_previous"],
    "chng_oi": ["changeInOI", "chngInOI", "oiChange", "changeinOI"],
    "pct_chng_oi": ["percentageChange", "pctChange", "perChangeInOI", "%chngInOI"],
    "ltp": ["lastPrice", "ltp", "LTP"],
}


def _get_proxies():
    """
    Optional: route requests through a scraping proxy (e.g. ScraperAPI,
    Bright Data, etc.) if configured in Streamlit secrets. This is the
    most reliable fix for NSE blocking cloud/datacenter IPs, since the
    proxy exits through a residential/rotating IP instead.

    To use: add to .streamlit/secrets.toml (or the Streamlit Cloud
    "Secrets" settings in the app dashboard):

        PROXY_URL = "http://user:pass@proxy-host:port"

    If not set, requests go direct (which works locally but may be
    blocked/slow on cloud hosts).
    """
    proxy_url = st.secrets.get("PROXY_URL") if hasattr(st, "secrets") else None
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_oi_spurts(retries: int = 4, base_delay: float = 3.0,
                     timeout: int = 30) -> pd.DataFrame:
    session = requests.Session()
    session.headers.update(HEADERS)
    proxies = _get_proxies()
    if proxies:
        session.proxies.update(proxies)

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            session.get(BASE_URL, timeout=timeout)
            time.sleep(1.5)
            session.get(HOME_URL, timeout=timeout)
            time.sleep(1.5)

            resp = session.get(API_URL, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("data", payload) if isinstance(payload, dict) else payload
            df = pd.DataFrame(rows)

            if df.empty:
                raise ValueError("Empty response from NSE.")
            return df

        except Exception as exc:
            last_error = exc
            if attempt < retries:
                # exponential backoff: 3s, 6s, 12s, ...
                time.sleep(base_delay * (2 ** (attempt - 1)))

    raise RuntimeError(
        f"Failed after {retries} attempts (last error: {last_error}). "
        "This is very likely NSE blocking/throttling requests from this "
        "server's IP range. See the README for the proxy workaround, or "
        "try the nsepython-based fallback."
    )


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for target, options in CANDIDATES.items():
        for opt in options:
            if opt in df.columns:
                rename_map[opt] = target
                break
    df = df.rename(columns=rename_map)
    ordered = [c for c in
               ["symbol", "instrument", "expiry", "oi_current",
                "oi_previous", "chng_oi", "pct_chng_oi", "ltp"]
               if c in df.columns]
    return df[ordered]


def main():
    st.set_page_config(page_title="NSE OI Spurts", layout="wide")
    st.title("NSE OI Spurts — Live Open Interest Movers")
    st.caption("Source: nseindia.com/market-data/oi-spurts")

    if st.button("🔄 Refresh data"):
        fetch_oi_spurts.clear()

    raw_df = None
    fetch_error = None
    try:
        with st.spinner("Fetching data from NSE (this can take up to ~60s)..."):
            raw_df = fetch_oi_spurts()
    except Exception as exc:
        fetch_error = exc

    if raw_df is None:
        # Fallback attempt using nsepython, which handles NSE's cookie/
        # anti-bot flow more robustly than plain requests.
        try:
            with st.spinner("Direct request failed, trying nsepython fallback..."):
                import nsepython
                raw_df = pd.DataFrame(
                    nsepython.nsefetch(
                        "https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings"
                    ).get("data", [])
                )
                if raw_df.empty:
                    raise ValueError("nsepython also returned no data.")
        except Exception as exc2:
            st.error(
                "Could not fetch data from NSE via either method. This is "
                "very likely NSE blocking/throttling requests from this "
                "server's IP range (common for Streamlit Cloud / GitHub "
                "Actions / other datacenter hosts).\n\n"
                f"Direct request error: {fetch_error}\n\n"
                f"nsepython fallback error: {exc2}\n\n"
                "**Options:** run this app locally on a home connection, "
                "configure a residential proxy via `PROXY_URL` in "
                "Streamlit secrets (see README), or fetch data locally on "
                "a schedule and have this app read from a CSV/database "
                "instead of calling NSE directly."
            )
            return

    df = normalize_columns(raw_df)
    for col in ["oi_current", "oi_previous", "chng_oi", "pct_chng_oi", "ltp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    st.subheader("Full OI Spurts Table")
    st.dataframe(df, use_container_width=True)

    if "pct_chng_oi" not in df.columns:
        st.warning(
            "Could not find a '% change in OI' column in the response. "
            "Raw columns received: " + ", ".join(raw_df.columns)
        )
        return

    df_sorted = df.sort_values("pct_chng_oi", ascending=False)
    top_row = df_sorted.iloc[0]

    st.subheader("🏆 Symbol with Top % Change in OI")
    col1, col2, col3 = st.columns(3)
    col1.metric("Symbol", str(top_row.get("symbol", "N/A")))
    col2.metric("% Change in OI", f"{top_row.get('pct_chng_oi', 0):.2f}%")
    col3.metric("LTP", top_row.get("ltp", "N/A"))

    st.subheader("Top 10 Symbols by % Change in OI")
    top10 = df_sorted.head(10)

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(top10["symbol"], top10["pct_chng_oi"], color="steelblue")
    bars[0].set_color("crimson")
    ax.set_xlabel("Symbol")
    ax.set_ylabel("% Change in OI")
    ax.set_title("Top 10 Symbols by % Change in Open Interest")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    st.pyplot(fig)


if __name__ == "__main__":
    main()
