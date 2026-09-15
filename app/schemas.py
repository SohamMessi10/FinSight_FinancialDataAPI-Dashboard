"""Pydantic schemas used for FastAPI request/response validation."""

from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TickerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str | None = None
    sector: str | None = None
    created_at: datetime


class DailyPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date_type
    open: float
    high: float
    low: float
    close: float
    volume: int


class MovingAverageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date_type
    ma_20: float | None = None
    ma_50: float | None = None
    ma_200: float | None = None


class AnomalyFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date_type
    is_anomaly: bool
    anomaly_score: float
    method: str


class IngestResponse(BaseModel):
    mode: str
    tickers_ingested: int
    rows_ingested: int
    duration_seconds: float


class ErrorDetail(BaseModel):
    detail: str
