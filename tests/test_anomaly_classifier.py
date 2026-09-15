"""Tests for the anomaly classifier's evaluation logic (app/ml/anomaly_classifier.py)."""

from app.ml.anomaly_classifier import (
    FEATURE_COLUMNS,
    engineer_features,
    evaluate_against_baseline,
    generate_labeled_evaluation_series,
    naive_baseline_predict,
)


def test_generate_labeled_series_is_reproducible():
    df1, labels1 = generate_labeled_evaluation_series(n_days=300, n_anomalies=10, seed=42)
    df2, labels2 = generate_labeled_evaluation_series(n_days=300, n_anomalies=10, seed=42)
    assert df1["close"].tolist() == df2["close"].tolist()
    assert (labels1 == labels2).all()
    assert labels1.sum() == 10


def test_engineer_features_drops_warmup_and_has_no_nans():
    df, _ = generate_labeled_evaluation_series(n_days=200, n_anomalies=5, seed=1)
    features = engineer_features(df)
    assert len(features) < len(df)
    assert set(FEATURE_COLUMNS).issubset(features.columns)
    assert not features[FEATURE_COLUMNS].isna().any().any()


def test_naive_baseline_flags_some_days():
    df, _ = generate_labeled_evaluation_series(n_days=750, n_anomalies=30, seed=42)
    features = engineer_features(df)
    preds = naive_baseline_predict(features)
    assert preds.dtype == bool
    assert 0 < preds.sum() < len(preds)


def test_model_beats_naive_baseline_on_f1():
    """The core evaluation claim: IsolationForest on multivariate features
    outperforms a naive same-day-return threshold, because roughly a third
    of the labeled anomalies (volatility bursts, volume spikes) have no
    extreme single-day return for the naive rule to catch.
    """
    results = evaluate_against_baseline()
    assert results["n_labeled_anomalies"] > 0
    assert results["model"]["f1"] > results["baseline"]["f1"]
    assert results["improvement_pct"]["f1"] > 0


def test_evaluation_is_reproducible_end_to_end():
    results1 = evaluate_against_baseline()
    results2 = evaluate_against_baseline()
    assert results1 == results2
