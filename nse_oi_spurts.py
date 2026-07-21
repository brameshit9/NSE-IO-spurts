"""
NSE "OI Spurts" scraper
------------------------
Source page : https://www.nseindia.com/market-data/oi-spurts
Underlying API (used by the page itself):
    https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings

This script:
1. Opens a session and visits the NSE homepage first (required to obtain
   valid cookies -- NSE blocks direct API calls without them).
2. Calls the OI-spurts API and loads the JSON into a pandas DataFrame.
3. Normalizes column names (NSE's JSON keys don't exactly match the
   on-page column labels).
4. Prints the full table.
5. Prints + highlights the symbol with the single highest "% change in OI".
6. Draws a bar chart (matplotlib) of the top 10 symbols by % change in OI,
   saving it as a PNG and showing it.

Requirements:
    pip install requests pandas matplotlib
"""

import sys
import time
import requests
import pandas as pd
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


def get_session() -> requests.Session:
    """Create a session and warm it up with NSE cookies."""
    session = requests.Session()
    session.headers.update(HEADERS)

    # First hit the homepage (needed to receive nsit / nseappid cookies)
    session.get(BASE_URL, timeout=10)
    time.sleep(1)
    # Then the actual page, which sets additional cookies used by the API
    session.get(HOME_URL, timeout=10)
    time.sleep(1)
    return session


def fetch_oi_spurts(session: requests.Session) -> pd.DataFrame:
    resp = session.get(API_URL, timeout=10)
    resp.raise_for_status()
    payload = resp.json()

    # The API usually wraps the rows in a "data" key
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError("No data returned by NSE API (empty response).")

    return df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map NSE's raw JSON field names to clean, predictable column names.
    NSE has used variants of these keys over time, so we try a few
    candidates for each target column.
    """
    candidates = {
        "symbol": ["symbol", "underlying", "Symbol"],
        "instrument": ["instrument", "instrumentType", "Instrument"],
        "expiry": ["expiryDate", "optExpiryDt", "expiry_dt", "Expiry"],
        "oi_current": [
            "latestOI", "openInterest", "currOI", "oi", "OI_current",
        ],
        "oi_previous": [
            "prevOI", "previousOI", "oiPrevious", "OI_previous",
        ],
        "chng_oi": [
            "changeInOI", "chngInOI", "oiChange", "changeinOI",
        ],
        "pct_chng_oi": [
            "percentageChange", "pctChange", "perChangeInOI", "%chngInOI",
        ],
        "ltp": ["lastPrice", "ltp", "LTP"],
    }

    rename_map = {}
    for target, options in candidates.items():
        for opt in options:
            if opt in df.columns:
                rename_map[opt] = target
                break

    df = df.rename(columns=rename_map)

    # Keep only the columns we recognized, in a sensible order
    ordered = [c for c in
               ["symbol", "instrument", "expiry", "oi_current",
                "oi_previous", "chng_oi", "pct_chng_oi", "ltp"]
               if c in df.columns]
    return df[ordered]


def main():
    print("Connecting to NSE and fetching OI Spurts data...")
    try:
        session = get_session()
        raw_df = fetch_oi_spurts(session)
    except Exception as exc:
        print(f"ERROR: could not fetch data from NSE: {exc}")
        print("NSE frequently blocks scripted requests. Try again in a "
              "few seconds, or run this from a normal residential IP "
              "(not a cloud/server IP), which NSE is less likely to block.")
        sys.exit(1)

    df = normalize_columns(raw_df)

    # Make sure numeric columns are actually numeric
    for col in ["oi_current", "oi_previous", "chng_oi", "pct_chng_oi", "ltp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print("\n=== Full OI Spurts table ===")
    print(df.to_string(index=False))

    if "pct_chng_oi" not in df.columns:
        print("\nCould not find a '% change in OI' column in the response; "
              "check df.columns / raw JSON keys and adjust normalize_columns().")
        return

    # Sort by % change in OI, descending
    df_sorted = df.sort_values("pct_chng_oi", ascending=False)
    top_row = df_sorted.iloc[0]

    print("\n=== Symbol with TOP % change in OI ===")
    print(top_row.to_string())

    # --- Chart: top 10 symbols by % change in OI ---
    top10 = df_sorted.head(10)

    plt.figure(figsize=(10, 6))
    bars = plt.bar(top10["symbol"], top10["pct_chng_oi"], color="steelblue")
    # Highlight the single top mover in a different color
    bars[0].set_color("crimson")

    plt.title("Top 10 Symbols by % Change in Open Interest (NSE OI Spurts)")
    plt.xlabel("Symbol")
    plt.ylabel("% Change in OI")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    out_path = "nse_oi_spurts_top10.png"
    plt.savefig(out_path, dpi=150)
    print(f"\nChart saved to: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
