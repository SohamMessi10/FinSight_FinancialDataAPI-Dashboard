"""Market data ingestion.

Pulls real daily OHLCV history from Yahoo Finance (via yfinance) for the
configured ticker universe. If Yahoo Finance is unreachable (no network
access, rate-limited, or blocked by an egress policy), automatically falls
back to generating realistic synthetic OHLCV data for the same real ticker
symbols, so the rest of the pipeline (DB, API, dashboard, ML) always has
data to work with. Which mode ran is always logged explicitly and returned
in the ingestion summary -- never silently substituted without a trace.

Moving averages (20/50/200-day SMA on close) are computed here as part of
ingestion and written to their own table.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.models import DailyPrice, MovingAverage, Ticker

logger = logging.getLogger("finsight.ingestion")

SEED = 42
_YAHOO_PROBE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
_PROBE_TIMEOUT_SECONDS = 4.0

# Real ticker symbols spanning tech, financials, healthcare, consumer,
# industrials, materials, utilities, real estate and communication services
# (roughly the S&P 500 universe plus a handful of large global ADRs). Used
# for both the real-data path and as labels for the synthetic-data fallback.
TICKER_UNIVERSE: list[str] = [
    "A", "AA", "AAL", "AAP", "AAPL", "ABBV", "ABC", "ABNB",
    "ABT", "ACGL", "ACN", "ADBE", "ADC", "ADI", "ADM", "ADP",
    "AEE", "AEO", "AEP", "AFL", "AFRM", "AIG", "AIZ", "AJG",
    "AKAM", "ALB", "ALE", "ALGN", "ALK", "ALL", "ALLE", "AMD",
    "AME", "AMGN", "AMP", "AMT", "AMZN", "AN", "ANET", "ANF",
    "ANSS", "AON", "AOS", "APA", "APD", "APH", "APO", "AR",
    "ARE", "ARES", "ARM", "ASH", "ASML", "ATO", "ATR", "AVA",
    "AVB", "AVGO", "AVY", "AWK", "AXL", "AXP", "AXS", "AZN",
    "AZO", "BA", "BABA", "BAC", "BALL", "BAX", "BBWI", "BBY",
    "BDX", "BEN", "BG", "BHP", "BIDU", "BIIB", "BJ", "BK",
    "BKH", "BKNG", "BKR", "BMY", "BNTX", "BOX", "BR", "BRO",
    "BRX", "BSX", "BUD", "BX", "BXP", "C", "CABO", "CAG",
    "CAH", "CARR", "CASY", "CAT", "CB", "CBOE", "CCI", "CCK",
    "CCL", "CDNS", "CDW", "CE", "CF", "CFG", "CHD", "CHEF",
    "CHRD", "CHRW", "CHTR", "CHX", "CI", "CIEN", "CINF", "CL",
    "CLF", "CLH", "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI",
    "CMS", "CNC", "CNP", "CNX", "COF", "COIN", "COLD", "COO",
    "COOP", "COP", "COR", "COST", "COTY", "CPB", "CPNG", "CPT",
    "CRL", "CRM", "CROX", "CRS", "CRSP", "CRWD", "CSCO", "CSX",
    "CTLT", "CTRA", "CTSH", "CUZ", "CVI", "CVS", "CVX", "D",
    "DAL", "DASH", "DBX", "DD", "DDOG", "DE", "DECK", "DELL",
    "DEO", "DFS", "DG", "DGX", "DHI", "DHR", "DINO", "DIS",
    "DK", "DKS", "DLR", "DLTR", "DOC", "DOCU", "DOV", "DOW",
    "DTE", "DUK", "DVN", "DXCM", "EA", "EBAY", "ECL", "ED",
    "EFX", "EGP", "EL", "ELAN", "ELV", "EMN", "EMR", "ENPH",
    "EOG", "EPAM", "EQIX", "EQR", "EQT", "ERIE", "ES", "ESS",
    "ESTC", "ETN", "ETSY", "EVR", "EVRG", "EXC", "EXPD", "EXR",
    "FAF", "FANG", "FAST", "FCX", "FDX", "FFIV", "FI", "FICO",
    "FIS", "FITB", "FL", "FLEX", "FMC", "FNF", "FOX", "FOXA",
    "FR", "FRT", "FTI", "FTNT", "FTV", "GD", "GDDY", "GE",
    "GEHC", "GEN", "GGG", "GILD", "GIS", "GL", "GLW", "GNRC",
    "GOOG", "GOOGL", "GPC", "GPK", "GPN", "GPS", "GRAB", "GRMN",
    "GS", "GSK", "GTLB", "GTN", "HAL", "HAS", "HBAN", "HCA",
    "HD", "HES", "HIG", "HII", "HIW", "HLT", "HMC", "HOG",
    "HOLX", "HON", "HOOD", "HP", "HPE", "HPQ", "HRL", "HSIC",
    "HST", "HSY", "HUBS", "HUM", "HUN", "IBM", "ICE", "ICLR",
    "IDA", "IDXX", "IEX", "IFF", "IHRT", "INCY", "INFY", "INTC",
    "INTU", "IP", "IPG", "IQV", "IR", "IRM", "ISRG", "IT",
    "ITW", "IVZ", "J", "JAZZ", "JBL", "JCI", "JD", "JJSF",
    "JKHY", "JNJ", "JNPR", "JPM", "K", "KBH", "KEY", "KEYS",
    "KHC", "KIM", "KKR", "KLAC", "KMB", "KMI", "KMX", "KO",
    "KR", "KRC", "L", "LANC", "LCID", "LEN", "LH", "LHX",
    "LI", "LIN", "LLY", "LMT", "LNC", "LNT", "LOGI", "LOW",
    "LRCX", "LULU", "LUMN", "LUV", "LVS", "LYB", "LYV", "MA",
    "MAA", "MAR", "MAS", "MAT", "MCD", "MCHP", "MCK", "MCO",
    "MDB", "MDLZ", "MDT", "MDU", "MELI", "MET", "META", "MGM",
    "MHK", "MKC", "MKTX", "MLM", "MMC", "MMM", "MO", "MOH",
    "MOS", "MP", "MPC", "MPWR", "MRK", "MRNA", "MRO", "MS",
    "MSCI", "MSFT", "MSI", "MTB", "MTCH", "MTD", "MU", "NAVI",
    "NCLH", "NDAQ", "NEE", "NEM", "NET", "NFLX", "NI", "NIO",
    "NJR", "NKE", "NNN", "NOC", "NOV", "NOW", "NSC", "NTAP",
    "NTGR", "NTRS", "NU", "NUE", "NVDA", "NVO", "NVR", "NVS",
    "NWE", "NWL", "NWS", "NWSA", "NYT", "O", "ODFL", "OFC",
    "OGE", "OGN", "OKE", "OKTA", "OLN", "OMC", "OMF", "ON",
    "ORCL", "ORLY", "OTIS", "OVV", "OXY", "PANW", "PARA", "PATH",
    "PAYC", "PAYX", "PBF", "PCAR", "PCTY", "PDD", "PECO", "PEG",
    "PEP", "PFE", "PFG", "PFGC", "PFSI", "PG", "PGR", "PH",
    "PHM", "PII", "PINS", "PKG", "PLD", "PLTR", "PM", "PNC",
    "PNR", "PNW", "PODD", "POOL", "POR", "PPG", "PPL", "PRGO",
    "PRU", "PSA", "PSX", "PTC", "PVH", "PWR", "PXD", "PYPL",
    "QCOM", "QRVO", "RBLX", "RCL", "RE", "REG", "REGN", "REXR",
    "RF", "RGA", "RIG", "RIO", "RIVN", "RJF", "RKT", "RL",
    "RMD", "RNR", "ROK", "ROL",
]
assert len(TICKER_UNIVERSE) == len(set(TICKER_UNIVERSE)), "duplicate tickers in universe"


@dataclass
class IngestionResult:
    mode: str  # "real", "synthetic", or "mixed"
    tickers_ingested: int
    rows_ingested: int
    duration_seconds: float


def get_ticker_universe(limit: int = 500) -> list[str]:
    """Return up to `limit` real ticker symbols from the configured universe."""
    return TICKER_UNIVERSE[:limit]


def _probe_network() -> bool:
    """Quick connectivity check against Yahoo Finance.

    Avoids letting yfinance hang/retry for minutes across hundreds of
    tickers when there's simply no route out (sandboxed CI, offline dev,
    a restrictive egress policy, etc).
    """
    try:
        resp = requests.get(_YAHOO_PROBE_URL, timeout=_PROBE_TIMEOUT_SECONDS)
        return resp.status_code == 200
    except requests.RequestException as exc:
        logger.info("Network probe to Yahoo Finance failed: %s", exc)
        return False


def _seed_for_symbol(symbol: str) -> int:
    """Deterministic per-symbol seed derived from the global SEED."""
    digest = hashlib.md5(symbol.encode("utf-8")).hexdigest()
    return (SEED + int(digest, 16)) % (2**31 - 1)


def _generate_synthetic_ohlcv(symbol: str, period_days: int) -> pd.DataFrame:
    """Generate a realistic-looking synthetic OHLCV series for one symbol.

    Uses geometric Brownian motion with a per-ticker drift/volatility regime
    (deterministic from `symbol`) plus occasional volatility-spike days, so
    downstream anomaly detection has genuine, varied signal to work with.
    """
    rng = np.random.default_rng(_seed_for_symbol(symbol))

    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=period_days)

    initial_price = rng.uniform(20.0, 400.0)
    annual_vol = rng.uniform(0.15, 0.45)
    annual_drift = rng.uniform(-0.05, 0.15)
    daily_sigma = annual_vol / np.sqrt(252)
    daily_mu = annual_drift / 252

    daily_returns = rng.normal(loc=daily_mu, scale=daily_sigma, size=period_days)

    # Inject occasional natural volatility-spike days (~1.5% of days) so the
    # series isn't purely smooth noise -- these are NOT the labeled ground
    # truth used for classifier evaluation (see app/ml/anomaly_classifier.py),
    # just realistic market texture for the demo dashboard/API to display.
    jump_mask = rng.random(period_days) < 0.015
    jump_shocks = rng.normal(loc=0.0, scale=daily_sigma * 6, size=period_days)
    daily_returns = np.where(jump_mask, daily_returns + jump_shocks, daily_returns)

    close = initial_price * np.cumprod(1.0 + daily_returns)
    close = np.maximum(close, 0.5)  # keep prices positive

    prev_close = np.concatenate([[initial_price], close[:-1]])
    overnight_gap = rng.normal(loc=0.0, scale=daily_sigma * 0.5, size=period_days)
    open_ = prev_close * (1.0 + overnight_gap)

    high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0.0, 0.005, period_days)))
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0.0, 0.005, period_days)))
    low = np.maximum(low, 0.25)

    base_volume = rng.uniform(1_000_000, 20_000_000)
    volume = (base_volume * (1.0 + 8.0 * np.abs(daily_returns))).astype(np.int64)

    return pd.DataFrame(
        {
            "date": dates.date,
            "open": open_.round(2),
            "high": high.round(2),
            "low": low.round(2),
            "close": close.round(2),
            "volume": volume,
        }
    )


def _fetch_real_ohlcv(symbol: str, period: str = "2y") -> pd.DataFrame | None:
    """Fetch real daily OHLCV history for one symbol via yfinance.

    Returns None (rather than raising) on any failure so the caller can
    fall back to synthetic data for that individual ticker.
    """
    import yfinance as yf  # imported lazily: only needed on the real-data path

    try:
        df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
    except Exception as exc:  # yfinance can raise a variety of exception types
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return None

    if df is None or df.empty:
        return None

    df = df.reset_index()
    df = df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["date", "open", "high", "low", "close", "volume"]]


def compute_moving_averages(price_df: pd.DataFrame) -> pd.DataFrame:
    """Compute 20/50/200-day simple moving averages on close price.

    Returns a DataFrame with columns: date, ma_20, ma_50, ma_200. Early rows
    with insufficient history get NaN (converted to SQL NULL on insert).
    """
    out = price_df[["date"]].copy()
    out["ma_20"] = price_df["close"].rolling(window=20, min_periods=20).mean()
    out["ma_50"] = price_df["close"].rolling(window=50, min_periods=50).mean()
    out["ma_200"] = price_df["close"].rolling(window=200, min_periods=200).mean()
    return out


def _get_or_create_ticker(db: Session, symbol: str) -> Ticker:
    ticker = db.query(Ticker).filter(Ticker.symbol == symbol).one_or_none()
    if ticker is None:
        ticker = Ticker(symbol=symbol)
        db.add(ticker)
        db.flush()  # assigns ticker.id without committing the transaction
    return ticker


def _replace_ticker_rows(db: Session, ticker_id: int, price_df: pd.DataFrame, ma_df: pd.DataFrame) -> int:
    """Idempotently replace a ticker's price/MA rows (delete then bulk insert)."""
    db.execute(delete(DailyPrice).where(DailyPrice.ticker_id == ticker_id))
    db.execute(delete(MovingAverage).where(MovingAverage.ticker_id == ticker_id))

    price_rows = [
        {
            "ticker_id": ticker_id,
            "date": row.date,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": int(row.volume),
        }
        for row in price_df.itertuples(index=False)
    ]
    ma_rows = [
        {
            "ticker_id": ticker_id,
            "date": row.date,
            "ma_20": None if pd.isna(row.ma_20) else float(row.ma_20),
            "ma_50": None if pd.isna(row.ma_50) else float(row.ma_50),
            "ma_200": None if pd.isna(row.ma_200) else float(row.ma_200),
        }
        for row in ma_df.itertuples(index=False)
    ]

    if price_rows:
        db.execute(insert(DailyPrice), price_rows)
    if ma_rows:
        db.execute(insert(MovingAverage), ma_rows)
    return len(price_rows)


def run_ingestion(db: Session, limit: int = 500, period_days: int = 500) -> IngestionResult:
    """Ingest OHLCV history + moving averages for up to `limit` tickers.

    Tries real data first (network permitting); any ticker that fails on
    the real path falls back to synthetic data individually. Logs which
    mode ran and returns a summary the API/CLI can report back honestly.
    """
    start = time.monotonic()
    symbols = get_ticker_universe(limit)

    network_available = _probe_network()
    if network_available:
        logger.info("Network probe succeeded; attempting real yfinance data for %d tickers", len(symbols))
    else:
        logger.warning(
            "Network probe to Yahoo Finance failed; falling back to synthetic OHLCV "
            "generation for all %d tickers (seed=%d)",
            len(symbols),
            SEED,
        )

    real_count = 0
    synthetic_count = 0
    total_rows = 0

    for i, symbol in enumerate(symbols, start=1):
        price_df: pd.DataFrame | None = None

        if network_available:
            price_df = _fetch_real_ohlcv(symbol, period=f"{max(period_days // 252, 1)}y")
            if price_df is not None and len(price_df) >= 200:
                real_count += 1
            else:
                price_df = None

        if price_df is None:
            price_df = _generate_synthetic_ohlcv(symbol, period_days)
            synthetic_count += 1

        ma_df = compute_moving_averages(price_df)
        ticker = _get_or_create_ticker(db, symbol)
        total_rows += _replace_ticker_rows(db, ticker.id, price_df, ma_df)

        if i % 50 == 0:
            db.commit()
            logger.info("Ingested %d/%d tickers", i, len(symbols))

    db.commit()

    if real_count and synthetic_count:
        mode = "mixed"
    elif real_count:
        mode = "real"
    else:
        mode = "synthetic"

    duration = time.monotonic() - start
    logger.info(
        "Ingestion complete: mode=%s real=%d synthetic=%d rows=%d duration=%.1fs",
        mode,
        real_count,
        synthetic_count,
        total_rows,
        duration,
    )
    return IngestionResult(
        mode=mode,
        tickers_ingested=len(symbols),
        rows_ingested=total_rows,
        duration_seconds=round(duration, 2),
    )


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal, init_db

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Run FinSight market data ingestion")
    parser.add_argument("--limit", type=int, default=500, help="number of tickers to ingest")
    parser.add_argument("--days", type=int, default=500, help="trading days of history per ticker")
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        result = run_ingestion(session, limit=args.limit, period_days=args.days)
        print(result)
    finally:
        session.close()
