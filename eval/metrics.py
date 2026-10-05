"""Pure-Python metrics (no third-party imports) so they are trivially unit-testable."""
LABELS = ["True", "False", "Misleading", "Unverified"]
BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]


def compute(rows: list[dict]) -> dict:
    """rows: [{"gold": str, "pred": str, "confidence": float}]. Failed runs must be excluded by the caller."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    confusion = {g: {p: 0 for p in LABELS} for g in LABELS}
    for r in rows:
        confusion[r["gold"]][r["pred"]] += 1

    correct = sum(r["gold"] == r["pred"] for r in rows)
    answered = [r for r in rows if r["pred"] != "Unverified"]
    wrong_answered = [r for r in answered if r["pred"] != r["gold"]]
    high_conf_wrong = [r for r in wrong_answered if r["confidence"] >= 0.8]

    per_class, f1s = {}, []
    for lab in LABELS:
        tp = confusion[lab][lab]
        fp = sum(confusion[g][lab] for g in LABELS if g != lab)
        fn = sum(confusion[lab][p] for p in LABELS if p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        support = tp + fn
        per_class[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": support}
        if support:
            f1s.append(f1)

    calibration = []
    for lo, hi in BINS:
        b = [r for r in answered if lo <= r["confidence"] < hi]
        if b:
            calibration.append({
                "range": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": len(b),
                "mean_confidence": sum(r["confidence"] for r in b) / len(b),
                "accuracy": sum(r["gold"] == r["pred"] for r in b) / len(b),
            })

    return {
        "n": n,
        "accuracy": correct / n,
        "macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
        "abstention_rate": 1 - len(answered) / n,
        "accuracy_when_answered": (sum(r["gold"] == r["pred"] for r in answered) / len(answered)) if answered else 0.0,
        "high_conf_wrong_rate": len(high_conf_wrong) / n,
        "confusion": confusion,
        "per_class": per_class,
        "calibration": calibration,
    }
