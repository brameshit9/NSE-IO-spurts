"""
NSE "OI Spurts" + Option Chain Drill-Down - Streamlit App
-----------------------------------------------------------
Source page : https://www.nseindia.com/market-data/oi-spurts
APIs used   :
    https://www.nseindia.com/api/live-analysis-oi-spurts-underlyings
    https://www.nseindia.com/api/option-chain-indices?symbol=<X>      (indices)
    https://www.nseindia.com/api/option-chain-equities?symbol=<X>     (stocks)

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

IMPORTANT: NSE blocks requests from many cloud/datacenter IPs. See README.md
for proxy / fallback workarounds if deployment fails.

DISCLAIMER: This app shows where Open Interest is concentrating according
to NSE's public data. It does NOT predict price direction and is not
financial advice. Options trading carries substantial risk of loss.
"""

import time
import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

BASE_URL = "https://www.nseindia.com"
HOME_URL = f"{BASE_URL}/market-data/oi-spurts"
OI_SPURTS_URL = f"{BASE_URL}/api/live-analysis-oi-spurts-underlyings"
OPTCHAIN_INDEX_URL = f"{BASE_URL}/api/option-chain-indices"
OPTCHAIN_EQUITY_URL = f"{BASE_URL}/api/option-chain-equities"

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}

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
    "ltp": ["lastPrice", "ltp", "LTP", "lastTradedPrice", "closePrice"],
}


def _get_proxies():
    """Optional residential proxy via Streamlit secrets: PROXY_URL = '...'"""
    proxy_url = st.secrets.get("PROXY_URL") if hasattr(st, "secrets") else None
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None


def _warmed_session(timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    proxies = _get_proxies()
    if proxies:
        session.proxies.update(proxies)
    session.get(BASE_URL, timeout=timeout)
    time.sleep(1)
    session.get(HOME_URL, timeout=timeout)
    time.sleep(1)
    return session


@st.cache_data(ttl=60, show_spinner=False)
def fetch_oi_spurts(retries: int = 4, base_delay: float = 3.0,
                     timeout: int = 30) -> pd.DataFrame:
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            session = _warmed_session(timeout)
            resp = session.get(OI_SPURTS_URL, timeout=timeout)
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
                time.sleep(base_delay * (2 ** (attempt - 1)))

    # Fallback: try nsepython if plain requests keeps failing
    try:
        import nsepython
        payload = nsepython.nsefetch(OI_SPURTS_URL)
        df = pd.DataFrame(payload.get("data", []))
        if not df.empty:
            return df
    except Exception:
        pass

    raise RuntimeError(
        f"Failed after {retries} attempts (last error: {last_error}). "
        "Likely NSE blocking this server's IP range."
    )


@st.cache_data(ttl=60, show_spinner=False)
def fetch_option_chain(symbol: str, retries: int = 3, timeout: int = 30) -> dict:
    url = OPTCHAIN_INDEX_URL if symbol in INDEX_SYMBOLS else OPTCHAIN_EQUITY_URL
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            session = _warmed_session(timeout)
            resp = session.get(url, params={"symbol": symbol}, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(3 * (2 ** (attempt - 1)))
    raise RuntimeError(f"Option chain fetch failed for {symbol}: {last_error}")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for target, options in CANDIDATES.items():
        for opt in options:
            if opt in df.columns:
                rename_map[opt] = target
                break
    df = df.rename(columns=rename_map)
    for col in ["oi_current", "oi_previous", "chng_oi", "ltp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute % change ourselves -- more reliable than guessing NSE's
    # field name for it, since it isn't always present in the payload.
    if "chng_oi" in df.columns and "oi_previous" in df.columns:
        df["pct_chng_oi"] = (df["chng_oi"] / df["oi_previous"].replace(0, pd.NA)) * 100
    elif "oi_current" in df.columns and "oi_previous" in df.columns:
        df["chng_oi"] = df["oi_current"] - df["oi_previous"]
        df["pct_chng_oi"] = (df["chng_oi"] / df["oi_previous"].replace(0, pd.NA)) * 100

    ordered = [c for c in
               ["symbol", "instrument", "expiry", "oi_current", "oi_previous",
                "chng_oi", "pct_chng_oi", "ltp"]
               if c in df.columns]
    return df[ordered]


def option_chain_to_df(raw: dict) -> pd.DataFrame:
    """Flatten NSE option-chain JSON into a per-strike CE/PE dataframe."""
    records = raw.get("records", {})
    data = records.get("data", [])
    rows = []
    for item in data:
        strike = item.get("strikePrice")
        ce = item.get("CE", {})
        pe = item.get("PE", {})
        rows.append({
            "strike": strike,
            "CE_OI": ce.get("openInterest", 0),
            "CE_chgOI": ce.get("changeinOpenInterest", 0),
            "CE_LTP": ce.get("lastPrice", 0),
            "PE_OI": pe.get("openInterest", 0),
            "PE_chgOI": pe.get("changeinOpenInterest", 0),
            "PE_LTP": pe.get("lastPrice", 0),
        })
    df = pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
    return df


def main():
    st.set_page_config(page_title="NSE OI Spurts", layout="wide")
    st.title("NSE OI Spurts — Live Open Interest Movers")
    st.caption("Source: nseindia.com/market-data/oi-spurts")

    if st.button("Refresh data"):
        fetch_oi_spurts.clear()
        fetch_option_chain.clear()

    try:
        with st.spinner("Fetching data from NSE..."):
            raw_df = fetch_oi_spurts()
    except Exception as exc:
        st.error(
            "Could not fetch data from NSE. This usually means NSE is "
            "blocking requests from this server's IP.\n\n"
            f"Details: {exc}"
        )
        return

    df = normalize_columns(raw_df)

    st.subheader("Full OI Spurts Table")
    st.dataframe(df, use_container_width=True)

    if "pct_chng_oi" not in df.columns or df["pct_chng_oi"].isna().all():
        st.warning(
            "Could not compute % change in OI (missing OI columns). "
            "Raw columns received: " + ", ".join(raw_df.columns)
        )
        return

    df_sorted = df.sort_values("pct_chng_oi", ascending=False)
    top_row = df_sorted.iloc[0]

    # --- Top mover callout ---
    st.subheader("Symbol with Top % Change in OI")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Symbol", str(top_row.get("symbol", "N/A")))
    c2.metric("% Chg in OI", f"{top_row.get('pct_chng_oi', 0):.2f}%")
    c3.metric("Chg in OI", f"{top_row.get('chng_oi', 0):,.0f}")
    ltp_val = top_row.get("ltp", None)
    c4.metric("LTP", f"₹{ltp_val:,.2f}" if pd.notna(ltp_val) else "N/A")

    # --- Chart 1: horizontal bar, top 10 movers by % change, red/green ---
    st.subheader("Top 10 Movers — % Change in OI")
    top10 = df_sorted.head(10).iloc[::-1]  # reverse for horizontal bar (top at top)
    colors = ["crimson" if v < 0 else "seagreen" for v in top10["pct_chng_oi"]]

    fig1, ax1 = plt.subplots(figsize=(9, 5))
    bars = ax1.barh(top10["symbol"], top10["pct_chng_oi"], color=colors)
    for bar, ltp in zip(bars, top10["ltp"]):
        label = f"{bar.get_width():+.2f}%"
        if pd.notna(ltp):
            label += f"  (₹{ltp:,.2f})"
        ax1.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, label,
                  va="center", ha="left" if bar.get_width() >= 0 else "right",
                  fontsize=9)
    ax1.set_xlabel("% Change in OI")
    ax1.set_title("Top 10 by % Change in OI (with LTP)")
    plt.tight_layout()
    st.pyplot(fig1)

    # --- Chart 2: Up/Down/Flat donut ---
    st.subheader("Market Breadth (by OI change direction)")
    up = int((df["chng_oi"] > 0).sum())
    down = int((df["chng_oi"] < 0).sum())
    flat = int((df["chng_oi"] == 0).sum())

    fig2, ax2 = plt.subplots(figsize=(4, 4))
    ax2.pie([up, down, flat], labels=[f"Up ({up})", f"Down ({down})", f"Flat ({flat})"],
            colors=["seagreen", "crimson", "gray"], autopct="%1.0f%%",
            wedgeprops=dict(width=0.4))
    ax2.set_title("OI Direction Breakdown")
    st.pyplot(fig2)

    # --- Option chain drill-down ---
    st.divider()
    st.subheader("Drill Down: Option Chain by Strike")
    st.caption(
        "Shows where Open Interest is currently concentrated per strike, "
        "for the symbol you pick. This is descriptive market data, not a "
        "trade recommendation."
    )

    symbol_choice = st.selectbox(
        "Choose a symbol to inspect its option chain",
        options=df_sorted["symbol"].tolist(),
        index=0,
    )

    if st.button(f"Load option chain for {symbol_choice}"):
        try:
            with st.spinner(f"Fetching option chain for {symbol_choice}..."):
                raw_chain = fetch_option_chain(symbol_choice)
                chain_df = option_chain_to_df(raw_chain)
        except Exception as exc:
            st.error(f"Could not fetch option chain: {exc}")
            chain_df = pd.DataFrame()

        if not chain_df.empty:
            st.dataframe(chain_df, use_container_width=True)

            top_ce = chain_df.loc[chain_df["CE_chgOI"].idxmax()]
            top_pe = chain_df.loc[chain_df["PE_chgOI"].idxmax()]

            cc1, cc2 = st.columns(2)
            cc1.metric("Call (CE) strike with highest OI buildup",
                       f"{top_ce['strike']:.0f}",
                       f"+{top_ce['CE_chgOI']:,.0f} OI, LTP ₹{top_ce['CE_LTP']:.2f}")
            cc2.metric("Put (PE) strike with highest OI buildup",
                       f"{top_pe['strike']:.0f}",
                       f"+{top_pe['PE_chgOI']:,.0f} OI, LTP ₹{top_pe['PE_LTP']:.2f}")

            fig3, ax3 = plt.subplots(figsize=(11, 5))
            width = (chain_df["strike"].diff().median() or 50) * 0.4
            ax3.bar(chain_df["strike"] - width / 2, chain_df["CE_chgOI"],
                    width=width, color="seagreen", label="Call (CE) Chg OI")
            ax3.bar(chain_df["strike"] + width / 2, chain_df["PE_chgOI"],
                    width=width, color="crimson", label="Put (PE) Chg OI")
            ax3.axhline(0, color="black", linewidth=0.8)
            ax3.set_xlabel("Strike Price")
            ax3.set_ylabel("Change in Open Interest")
            ax3.set_title(f"{symbol_choice} — Change in OI by Strike (Calls vs Puts)")
            ax3.legend()
            plt.tight_layout()
            st.pyplot(fig3)

            st.info(
                "Heavy call OI buildup at a strike often reflects where "
                "traders expect resistance; heavy put OI buildup often "
                "reflects expected support. This is a common heuristic, "
                "not a guarantee — NSE data reflects existing positioning, "
                "not a forecast. Always size positions according to your "
                "own risk tolerance."
            )
        else:
            st.warning("No option chain data returned for this symbol.")


if __name__ == "__main__":
    main()
