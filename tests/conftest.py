"""Shared pytest fixtures.

Tests run against a throwaway SQLite database (set via DATABASE_URL before
app.db is imported) instead of a live Postgres instance, so `pytest` works
standalone with no docker-compose services running.
"""

import os
import tempfile
from datetime import date

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/finsight_test.db")

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import AnomalyFlag, DailyPrice, MovingAverage, Ticker

init_db()


@pytest.fixture(autouse=True)
def _clean_db():
    """Wipe all rows before every test so tests don't leak state into each other."""
    session = SessionLocal()
    try:
        session.query(AnomalyFlag).delete()
        session.query(MovingAverage).delete()
        session.query(DailyPrice).delete()
        session.query(Ticker).delete()
        session.commit()
    finally:
        session.close()
    yield


@pytest.fixture()
def seeded_ticker() -> str:
    """Insert one ticker with 3 days of prices/MAs and one anomaly flag."""
    session = SessionLocal()
    ticker = Ticker(symbol="TEST", name="Test Corp", sector="Technology")
    session.add(ticker)
    session.flush()

    for i in range(3):
        d = date(2024, 1, i + 1)
        session.add(
            DailyPrice(
                ticker_id=ticker.id,
                date=d,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1_000_000,
            )
        )
        session.add(MovingAverage(ticker_id=ticker.id, date=d, ma_20=100.0, ma_50=None, ma_200=None))

    session.add(
        AnomalyFlag(
            ticker_id=ticker.id,
            date=date(2024, 1, 2),
            is_anomaly=True,
            anomaly_score=1.5,
            method="isolation_forest",
        )
    )
    session.commit()
    symbol = ticker.symbol
    session.close()
    return symbol


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
