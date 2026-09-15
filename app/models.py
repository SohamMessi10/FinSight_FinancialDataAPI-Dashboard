"""SQLAlchemy ORM models for the FinSight schema.

Four tables:
- tickers: the security universe
- daily_prices: raw OHLCV bars
- moving_averages: 20/50/200-day SMAs derived from daily_prices
- anomaly_flags: output of the ML anomaly classifier
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Ticker(Base):
    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    daily_prices: Mapped[list["DailyPrice"]] = relationship(
        back_populates="ticker", cascade="all, delete-orphan"
    )
    moving_averages: Mapped[list["MovingAverage"]] = relationship(
        back_populates="ticker", cascade="all, delete-orphan"
    )
    anomaly_flags: Mapped[list["AnomalyFlag"]] = relationship(
        back_populates="ticker", cascade="all, delete-orphan"
    )


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("ticker_id", "date", name="uq_daily_prices_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)

    ticker: Mapped["Ticker"] = relationship(back_populates="daily_prices")


class MovingAverage(Base):
    __tablename__ = "moving_averages"
    __table_args__ = (UniqueConstraint("ticker_id", "date", name="uq_moving_averages_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    ma_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma_200: Mapped[float | None] = mapped_column(Float, nullable=True)

    ticker: Mapped["Ticker"] = relationship(back_populates="moving_averages")


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"
    __table_args__ = (
        UniqueConstraint("ticker_id", "date", "method", name="uq_anomaly_flags_ticker_date_method"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="isolation_forest")

    ticker: Mapped["Ticker"] = relationship(back_populates="anomaly_flags")
