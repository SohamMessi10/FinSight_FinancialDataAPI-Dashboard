"""API endpoint tests using FastAPI's TestClient (see tests/conftest.py for fixtures)."""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_tickers_empty(client):
    resp = client.get("/tickers")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_tickers_seeded(client, seeded_ticker):
    resp = client.get("/tickers")
    assert resp.status_code == 200
    symbols = [t["symbol"] for t in resp.json()]
    assert seeded_ticker in symbols


def test_get_prices(client, seeded_ticker):
    resp = client.get(f"/prices/{seeded_ticker}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    dates = [row["date"] for row in data]
    assert dates == sorted(dates)  # oldest first


def test_get_prices_not_found(client):
    resp = client.get("/prices/NOPE")
    assert resp.status_code == 404


def test_get_prices_limit(client, seeded_ticker):
    resp = client.get(f"/prices/{seeded_ticker}", params={"limit": 1})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_moving_averages(client, seeded_ticker):
    resp = client.get(f"/prices/{seeded_ticker}/moving-averages")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["ma_20"] == 100.0
    assert data[0]["ma_50"] is None


def test_get_anomalies_only_flagged(client, seeded_ticker):
    resp = client.get(f"/anomalies/{seeded_ticker}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_anomaly"] is True
    assert data[0]["date"] == "2024-01-02"


def test_get_anomalies_not_found(client):
    resp = client.get("/anomalies/NOPE")
    assert resp.status_code == 404
