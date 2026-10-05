"""Evidence quality: independent-source clustering and a computed (not self-reported) confidence."""
import re

SIM_THRESHOLD = 0.5
FACT_CHECK_TYPES = {"fact_check_db", "fact_check_api"}


def _shingles(text: str, k: int = 5) -> set[str]:
    words = re.findall(r"[\w\u0900-\u0D7F]+", (text or "").lower())
    if not words:
        return set()
    return {" ".join(words[i:i + k]) for i in range(max(1, len(words) - k + 1))}


def similarity(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    host = (m.group(1) if m else "").lower()
    return host[4:] if host.startswith("www.") else host


def assign_clusters(items: list[dict]) -> None:
    """Items from the same site, or with near-duplicate text (syndicated copies), share a cluster id."""
    reps: list[tuple[int, str, str]] = []  # (cluster id, domain, text)
    for it in items:
        text = f"{it.get('title', '')} {it.get('snippet', '')}"
        dom = _domain(it.get("url", ""))
        for cid, rdom, rtext in reps:
            if (dom and dom == rdom) or similarity(text, rtext) >= SIM_THRESHOLD:
                it["cluster"] = cid
                break
        else:
            cid = len(reps) + 1
            reps.append((cid, dom, text))
            it["cluster"] = cid


def _aligned(verdict: str, items: list[dict], stances: dict[str, str]) -> list[dict]:
    if verdict == "True":
        want = {"supports"}
    elif verdict == "False":
        want = {"refutes"}
    elif verdict == "Misleading":
        want = {"supports", "refutes"}
    else:
        return []
    return [it for it in items if stances.get(it["id"]) in want]


def aligned(verdict: str, items: list[dict], stances: dict[str, str]) -> bool:
    return bool(_aligned(verdict, items, stances))


def computed_confidence(verdict: str, items: list[dict], stances: dict[str, str],
                        model_conf: float) -> tuple[float, dict]:
    """Heuristic evidence-strength score. The weights are starting points: tune them against your eval run."""
    breakdown = {"model_confidence": round(model_conf, 2), "independent_sources": 0,
                 "best_reliability": 0.0, "fact_checker_backed": False, "conflicting_sources": 0}
    if verdict not in {"True", "False", "Misleading"}:
        return round(min(model_conf, 0.6), 2), breakdown

    good = _aligned(verdict, items, stances)
    if not good:
        return 0.2, breakdown
    opposite = {"True": "refutes", "False": "supports"}.get(verdict)
    opposing = [it for it in items if opposite and stances.get(it["id"]) == opposite]

    n_indep = len({it.get("cluster", it["id"]) for it in good})
    best = max(it["credibility"] for it in good)
    fc = any(it["source_type"] in FACT_CHECK_TYPES and it["credibility"] >= 0.8 for it in good)

    score = 0.30 + 0.35 * best + 0.10 * min(n_indep - 1, 2) + (0.10 if fc else 0.0)
    if any(it["credibility"] >= 0.7 for it in opposing):
        score *= 0.6
    elif opposing:
        score *= 0.85
    breakdown.update(independent_sources=n_indep, best_reliability=round(best, 2),
                     fact_checker_backed=fc, conflicting_sources=len(opposing))
    return round(max(0.05, min(score, 0.95)), 2), breakdown
