"""FinSight Streamlit dashboard.

Talks only to the FastAPI backend over HTTP (never touches Postgres
directly), demonstrating the same separation-of-concerns the API layer
enforces: the dashboard is just another API consumer.
"""

import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 10

st.set_page_config(page_title="FinSight Dashboard", layout="wide")


def _api_get(path: str, params: dict | None = None) -> list | dict | None:
    try:
        resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        st.error(f"Could not reach FinSight API at {API_BASE_URL}{path}: {exc}")
        return None


@st.cache_data(ttl=60)
def get_tickers() -> list[dict]:
    return _api_get("/tickers") or []


@st.cache_data(ttl=60)
def get_prices(symbol: str, limit: int = 500) -> list[dict]:
    return _api_get(f"/prices/{symbol}", params={"limit": limit}) or []


@st.cache_data(ttl=60)
def get_moving_averages(symbol: str, limit: int = 500) -> list[dict]:
    return _api_get(f"/prices/{symbol}/moving-averages", params={"limit": limit}) or []


@st.cache_data(ttl=60)
def get_anomalies(symbol: str) -> list[dict]:
    return _api_get(f"/anomalies/{symbol}", params={"only_flagged": True}) or []


def build_price_chart(prices: pd.DataFrame, mas: pd.DataFrame, anomalies: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices["date"], y=prices["close"], name="Close", line=dict(color="#2563eb")))

    for col, label, color in [("ma_20", "MA 20", "#f59e0b"), ("ma_50", "MA 50", "#10b981"), ("ma_200", "MA 200", "#ef4444")]:
        if col in mas.columns and mas[col].notna().any():
            fig.add_trace(go.Scatter(x=mas["date"], y=mas[col], name=label, line=dict(color=color, width=1.5)))

    if not anomalies.empty:
        merged = anomalies.merge(prices[["date", "close"]], on="date", how="left")
        fig.add_trace(
            go.Scatter(
                x=merged["date"],
                y=merged["close"],
                mode="markers",
                name="Anomaly",
                marker=dict(color="red", size=10, symbol="x"),
            )
        )

    fig.update_layout(
        title=f"{symbol} -- price, moving averages, and flagged anomalies",
        xaxis_title="Date",
        yaxis_title="Price",
        height=550,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def build_summary_table(symbols: list[str]) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        prices = get_prices(symbol, limit=2)
        anomalies = get_anomalies(symbol)
        if not prices:
            continue
        latest = prices[-1]
        prev_close = prices[-2]["close"] if len(prices) > 1 else latest["close"]
        pct_change = (latest["close"] - prev_close) / prev_close * 100 if prev_close else 0.0
        rows.append(
            {
                "Ticker": symbol,
                "Latest Close": latest["close"],
                "1D Change %": round(pct_change, 2),
                "Anomalies Flagged": len(anomalies),
            }
        )
    return pd.DataFrame(rows)


st.title("FinSight -- Financial Data Dashboard")

tickers = get_tickers()
if not tickers:
    st.warning(
        "No tickers loaded yet (or the API is unreachable). Start the API and run "
        "`POST /ingest`, then refresh this page."
    )
    st.stop()

symbols = sorted(t["symbol"] for t in tickers)

with st.sidebar:
    st.header("Controls")
    selected_symbol = st.selectbox("Ticker", symbols, index=0)
    history_days = st.slider("Price history (trading days)", min_value=60, max_value=500, value=250, step=10)
    summary_size = st.slider("Tickers in summary table", min_value=5, max_value=min(100, len(symbols)), value=20, step=5)

price_rows = get_prices(selected_symbol, limit=history_days)
ma_rows = get_moving_averages(selected_symbol, limit=history_days)
anomaly_rows = get_anomalies(selected_symbol)

if price_rows:
    prices_df = pd.DataFrame(price_rows)
    prices_df["date"] = pd.to_datetime(prices_df["date"])
    mas_df = pd.DataFrame(ma_rows)
    if not mas_df.empty:
        mas_df["date"] = pd.to_datetime(mas_df["date"])
    anomalies_df = pd.DataFrame(anomaly_rows)
    if not anomalies_df.empty:
        anomalies_df["date"] = pd.to_datetime(anomalies_df["date"])

    latest = prices_df.iloc[-1]
    col1, col2, col3 = st.columns(3)
    col1.metric("Latest Close", f"${latest['close']:.2f}")
    col2.metric("Latest Volume", f"{int(latest['volume']):,}")
    col3.metric("Anomalies Flagged", len(anomalies_df))

    st.plotly_chart(build_price_chart(prices_df, mas_df, anomalies_df, selected_symbol), use_container_width=True)

    if not anomalies_df.empty:
        st.subheader("Flagged anomaly days")
        display_df = anomalies_df[["date", "anomaly_score", "method"]].copy()
        display_df["date"] = display_df["date"].dt.date
        st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.info(f"No price history for {selected_symbol} yet. Run `POST /ingest` on the API first.")

st.subheader("Ticker summary")
with st.spinner("Loading summary..."):
    summary_df = build_summary_table(symbols[:summary_size])
st.dataframe(summary_df, use_container_width=True, hide_index=True)
