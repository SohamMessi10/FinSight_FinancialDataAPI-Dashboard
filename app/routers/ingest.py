"""Ingestion-trigger endpoint.

The only place in the serving layer that talks to the ingestion and ML
modules -- routes never touch yfinance/IsolationForest internals directly,
and ingestion/ML never import FastAPI. That's the modular boundary between
ingestion, storage, and serving.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion import run_ingestion
from app.ml.anomaly_classifier import run_anomaly_detection
from app.schemas import IngestResponse

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
def trigger_ingest(
    limit: int = Query(default=500, ge=1, le=500, description="number of tickers to ingest"),
    days: int = Query(default=500, ge=200, le=1500, description="trading days of history per ticker"),
    db: Session = Depends(get_db),
):
    """Refresh market data (real-or-synthetic, auto-detected) and re-run anomaly detection."""
    result = run_ingestion(db, limit=limit, period_days=days)
    run_anomaly_detection(db)
    return IngestResponse(
        mode=result.mode,
        tickers_ingested=result.tickers_ingested,
        rows_ingested=result.rows_ingested,
        duration_seconds=result.duration_seconds,
    )
