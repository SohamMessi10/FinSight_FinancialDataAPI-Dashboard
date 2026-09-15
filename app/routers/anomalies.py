"""Anomaly flag endpoint for a single ticker."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AnomalyFlag, Ticker
from app.schemas import AnomalyFlagOut

router = APIRouter(tags=["anomalies"])


@router.get("/anomalies/{ticker}", response_model=list[AnomalyFlagOut])
def get_anomalies(
    ticker: str,
    only_flagged: bool = Query(default=True, description="if true, return only days flagged anomalous"),
    db: Session = Depends(get_db),
):
    """Return anomaly-detection results for a ticker, oldest first."""
    t = db.query(Ticker).filter(Ticker.symbol == ticker.upper()).one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    query = db.query(AnomalyFlag).filter(AnomalyFlag.ticker_id == t.id)
    if only_flagged:
        query = query.filter(AnomalyFlag.is_anomaly.is_(True))
    return query.order_by(AnomalyFlag.date).all()
