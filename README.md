# FinSight -- Financial Data API & Dashboard

A full-stack market-data platform: FastAPI backend, PostgreSQL storage, a
scikit-learn anomaly detector, and a Streamlit dashboard, containerized
with Docker.

- 500 real ticker symbols, daily OHLCV + 20/50/200-day moving averages
- Auto-detecting ingestion: real Yahoo Finance data when reachable,
  realistic synthetic data (fixed seed) when it isn't -- always logged
- IsolationForest anomaly detector benchmarked against a naive std-dev
  baseline on labeled synthetic ground truth: **+63.5% F1**, **+112.5%
  recall** (see `reports/case_study.md` for the full methodology and
  real, reproduced numbers -- not invented ones)
- Clean module boundaries: ingestion, storage/models, ML, and the API
  routes are separate modules that only talk through the DB schema and
  function calls (`app/routers/*.py`)

## Project structure

```
app/
  main.py                FastAPI app (wires up routers)
  routers/                tickers, prices, anomalies, ingest endpoints
  ingestion.py            yfinance / synthetic-fallback data ingestion
  models.py                SQLAlchemy models
  schemas.py                Pydantic response models
  db.py                    DB engine/session/init
  ml/anomaly_classifier.py  IsolationForest + baseline evaluation
dashboard/
  streamlit_app.py         dashboard (calls the API only, never the DB)
docker/
  Dockerfile.api
  Dockerfile.dashboard
docker-compose.yml
reports/
  case_study.md            architecture, methodology, real measured results
  deployment_guide.md      AWS EC2 guide (documented, not yet executed -- see file)
tests/
requirements.txt
```

## Quickstart: docker-compose (recommended)

```bash
docker-compose up --build
```

This starts Postgres, the API (`:8000`), and the dashboard (`:8501`). Then
load data:

```bash
curl -X POST "http://localhost:8000/ingest?limit=500&days=500"
```

Open `http://localhost:8000/docs` for the interactive API docs, or
`http://localhost:8501` for the dashboard.

> **Honesty note:** this exact `docker-compose up --build` was written and
> its `docker-compose.yml`/Dockerfiles were syntax-validated
> (`docker compose config`), but could not be run to completion in the
> sandbox this project was built in -- outbound access to Docker Hub
> (needed to pull the `python:3.11-slim` and `postgres:16-alpine` base
> images) is blocked by that sandbox's network policy. Every Python module
> was instead run and verified natively end-to-end (ingestion -> Postgres
> -> API -> ML -> dashboard, see below and `reports/case_study.md`). On a
> normal machine with internet access, `docker-compose up --build` should
> just work -- if it doesn't, that's a real bug worth reporting.

### Docker-compose smoke test (do this yourself once)

Since this can't be verified in CI/this sandbox, here's exactly how to
confirm it works on your machine:

```bash
docker-compose up --build -d
docker-compose ps                       # expect postgres, api, dashboard all "healthy"/"running"
curl http://localhost:8000/health       # expect {"status":"ok"}
curl -X POST "http://localhost:8000/ingest?limit=20&days=260"   # small batch, ~10-20s
curl http://localhost:8000/tickers | head -c 300
open http://localhost:8501              # (or just visit it in a browser)
docker-compose logs api | tail -50      # check for errors
docker-compose down                     # add -v to also drop the postgres volume
```

If any service isn't healthy, `docker-compose logs <service>` is the first
thing to check.

## Running without Docker (what was actually verified)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Point at a local Postgres (or use docker run postgres:16-alpine)
export POSTGRES_HOST=localhost POSTGRES_USER=finsight POSTGRES_PASSWORD=finsight POSTGRES_DB=finsight

python -m app.ingestion --limit 500 --days 500     # ~26s measured locally
python -c "from app.db import SessionLocal; from app.ml.anomaly_classifier import run_anomaly_detection; s=SessionLocal(); run_anomaly_detection(s); s.close()"  # ~110s for 500 tickers

uvicorn app.main:app --reload &
streamlit run dashboard/streamlit_app.py
```

## Tests

```bash
pytest tests/ -v
```

14 tests: FastAPI `TestClient` coverage for every endpoint (using a
throwaway SQLite DB, no Postgres required), plus reproducibility and
model-vs-baseline tests for the anomaly classifier's evaluation logic.

## ML evaluation (reproducible, fixed seed)

```bash
python -m app.ml.anomaly_classifier
```

Prints accuracy/precision/recall/F1 for the IsolationForest model vs. the
naive std-dev baseline on a labeled synthetic series with 30 injected
anomalies (return shocks, volatility bursts, volume spikes). See
`reports/case_study.md` for the full write-up of what these numbers mean
and why F1 (not raw accuracy) is the headline metric here.

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | liveness check |
| GET | `/tickers` | list all ingested tickers |
| GET | `/prices/{ticker}` | daily OHLCV history (`?limit=`) |
| GET | `/prices/{ticker}/moving-averages` | 20/50/200-day SMAs (`?limit=`) |
| GET | `/anomalies/{ticker}` | flagged anomaly days (`?only_flagged=false` for all scored days) |
| POST | `/ingest` | refresh data + re-run anomaly detection (`?limit=&days=`) |

## Reports

- [`reports/case_study.md`](reports/case_study.md) -- architecture diagram,
  methodology, and real measured results (ticker coverage, ingestion/API
  timings, ML accuracy improvement).
- [`reports/deployment_guide.md`](reports/deployment_guide.md) -- AWS EC2
  deployment guide. Explicitly marked as documented-but-not-yet-executed.
