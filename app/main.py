"""FastAPI application entrypoint.

Wires together the modular routers (tickers, prices, anomalies, ingest).
Each router only depends on `app.db.get_db` and the SQLAlchemy models; the
ingestion and ML modules never import FastAPI. That boundary is the real
separation between ingestion, storage, and serving.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routers import anomalies, ingest, prices, tickers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="FinSight Financial Data API",
    description="Market data ingestion, storage, and ML-based anomaly detection API.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Liveness/readiness check used by the docker-compose healthcheck."""
    return {"status": "ok"}


app.include_router(tickers.router)
app.include_router(prices.router)
app.include_router(anomalies.router)
app.include_router(ingest.router)
