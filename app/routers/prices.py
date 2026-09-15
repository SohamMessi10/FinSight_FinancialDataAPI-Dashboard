"""Price and moving-average endpoints for a single ticker."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DailyPrice, MovingAverage, Ticker
from app.schemas import DailyPriceOut, MovingAverageOut

router = APIRouter(tags=["prices"])


def _get_ticker_or_404(db: Session, symbol: str) -> Ticker:
    ticker = db.query(Ticker).filter(Ticker.symbol == symbol.upper()).one_or_none()
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{symbol}' not found")
    return ticker


@router.get("/prices/{ticker}", response_model=list[DailyPriceOut])
def get_prices(
    ticker: str,
    limit: int = Query(default=500, ge=1, le=5000, description="most recent N trading days"),
    db: Session = Depends(get_db),
):
    """Return the most recent daily OHLCV bars for a ticker, oldest first."""
    t = _get_ticker_or_404(db, ticker)
    rows = (
        db.query(DailyPrice)
        .filter(DailyPrice.ticker_id == t.id)
        .order_by(DailyPrice.date.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


@router.get("/prices/{ticker}/moving-averages", response_model=list[MovingAverageOut])
def get_moving_averages(
    ticker: str,
    limit: int = Query(default=500, ge=1, le=5000, description="most recent N trading days"),
    db: Session = Depends(get_db),
):
    """Return the most recent 20/50/200-day moving averages for a ticker, oldest first."""
    t = _get_ticker_or_404(db, ticker)
    rows = (
        db.query(MovingAverage)
        .filter(MovingAverage.ticker_id == t.id)
        .order_by(MovingAverage.date.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))
