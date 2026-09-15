"""Ticker listing endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Ticker
from app.schemas import TickerOut

router = APIRouter(tags=["tickers"])


@router.get("/tickers", response_model=list[TickerOut])
def list_tickers(db: Session = Depends(get_db)):
    """Return every ticker currently loaded in the database."""
    return db.query(Ticker).order_by(Ticker.symbol).all()
