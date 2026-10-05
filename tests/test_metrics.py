from eval import metrics


def test_metrics_basic():
    rows = [
        {"gold": "True", "pred": "True", "confidence": 0.9},
        {"gold": "False", "pred": "True", "confidence": 0.85},   # high-confidence wrong
        {"gold": "False", "pred": "Unverified", "confidence": 0.3},  # abstain
        {"gold": "False", "pred": "False", "confidence": 0.6},
    ]
    m = metrics.compute(rows)
    assert m["n"] == 4 and m["accuracy"] == 0.5
    assert m["abstention_rate"] == 0.25
    assert abs(m["accuracy_when_answered"] - 2 / 3) < 1e-9
    assert m["high_conf_wrong_rate"] == 0.25
    assert m["confusion"]["False"]["True"] == 1
    assert metrics.compute([]) == {"n": 0}
