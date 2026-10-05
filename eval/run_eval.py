"""Evaluate the verifier on labelled claims and write a markdown report.

Examples
  python -m eval.run_eval --data eval/sample_claims.jsonl --modes baseline rag full
  python -m eval.run_eval --data data/liar/test.tsv --format liar --limit 100 \
      --modes baseline rag full --exclude-domain politifact.com

Modes (ablations)
  baseline  Claude alone, no retrieval (shows what the LLM "knows" from memory)
  rag       retrieval + verdict, verification pass OFF
  full      retrieval + verdict + verification pass (the shipped pipeline)

--exclude-domain drops results from those publishers so a benchmark claim cannot retrieve its own
fact-check. Run once with it and once without, and report both.
"""
import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from app.services import evidence as ev
from app.services.llm import start_usage, structured_call
from app.services.verify import VERDICTS, build_graph
from eval import datasets, metrics

BASELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": VERDICTS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["verdict", "confidence"],
}
BASELINE_SYSTEM = (
    "You are a fact-checker with NO access to search or documents. Judge the claim from your own knowledge. "
    "Answer Unverified when you are not sure. Confidence must reflect how likely your verdict is correct."
)


async def predict(mode: str, claim: str, graph, exclude: tuple[str, ...]) -> dict:
    ev.EXCLUDE_DOMAINS.set(exclude)  # per-task context, so concurrent runs do not interfere
    usage = start_usage()
    if mode == "baseline":
        out = await structured_call(BASELINE_SYSTEM, claim, "submit_verdict", "Submit verdict", BASELINE_SCHEMA)
        return {"pred": out["verdict"], "confidence": float(out["confidence"]),
                "tokens": usage["input_tokens"] + usage["output_tokens"]}
    state = {"content": claim, "input_type": "text", "verification": "full" if mode == "full" else "off"}
    result = (await graph.ainvoke(state))["result"]
    pred = "Unverified" if result["verdict"] == "Not Checkable" else result["verdict"]
    return {"pred": pred, "confidence": float(result["confidence"]),
            "tokens": usage["input_tokens"] + usage["output_tokens"],
            "citations": sum(len(c.get("citations", [])) for c in result.get("claims", []))}


async def run_mode(mode: str, rows: list[dict], concurrency: int, exclude: tuple[str, ...]) -> list[dict]:
    graph = build_graph() if mode != "baseline" else None
    sem = asyncio.Semaphore(concurrency)

    async def one(i: int, r: dict) -> dict:
        async with sem:
            t0 = time.perf_counter()
            try:
                out = await predict(mode, r["claim"], graph, exclude)
                err = None
            except Exception as exc:  # noqa: BLE001  (one failure must not kill a long run)
                out, err = {}, f"{exc.__class__.__name__}: {exc}"
            print(f"[{mode}] {i + 1}/{len(rows)} gold={r['label']} pred={out.get('pred', 'ERROR')}", flush=True)
            return {"claim": r["claim"], "gold": r["label"], "error": err,
                    "seconds": round(time.perf_counter() - t0, 2), **out}

    return await asyncio.gather(*(one(i, r) for i, r in enumerate(rows)))


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render(runs: dict[str, list[dict]], meta: dict) -> str:
    md = [f"# Evaluation report\n", f"- Generated: {meta['when']}", f"- Dataset: `{meta['data']}` ({meta['n']} claims)",
          f"- Model: `{meta['model']}`", f"- Excluded domains: {', '.join(meta['exclude']) or 'none'}", ""]
    scored = {m: metrics.compute([r for r in rows if not r["error"]]) for m, rows in runs.items()}

    md += ["## Summary", "", "| Mode | Answered rows | Failed | Accuracy | Macro-F1 | Abstain | Acc. when answered | High-conf wrong | Avg s/claim | Avg tokens |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for m, s in scored.items():
        rows = runs[m]
        failed = sum(1 for r in rows if r["error"])
        if not s.get("n"):
            md.append(f"| {m} | 0 | {failed} | - | - | - | - | - | - | - |")
            continue
        avg = sum(r["seconds"] for r in rows) / len(rows)
        avg_tok = sum(r.get("tokens", 0) for r in rows) / len(rows)
        md.append(f"| {m} | {s['n']} | {failed} | {pct(s['accuracy'])} | {s['macro_f1']:.3f} | {pct(s['abstention_rate'])} | "
                  f"{pct(s['accuracy_when_answered'])} | {pct(s['high_conf_wrong_rate'])} | {avg:.1f} | {avg_tok:,.0f} |")
    md += ["", "*High-conf wrong = share of all claims answered with confidence >= 0.8 and the wrong verdict.*", ""]

    for m, s in scored.items():
        if not s.get("n"):
            continue
        md += [f"## {m}", "", "**Confusion matrix** (rows = gold, columns = predicted)", "",
               "| gold \\ pred | " + " | ".join(metrics.LABELS) + " |", "|---|" + "---|" * len(metrics.LABELS)]
        for g in metrics.LABELS:
            md.append(f"| {g} | " + " | ".join(str(s["confusion"][g][p]) for p in metrics.LABELS) + " |")
        md += ["", "**Per class**", "", "| Class | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
        for lab, c in s["per_class"].items():
            md.append(f"| {lab} | {c['precision']:.2f} | {c['recall']:.2f} | {c['f1']:.2f} | {c['support']} |")
        if s["calibration"]:
            md += ["", "**Calibration** (answered claims only)", "", "| Confidence band | n | Mean confidence | Actual accuracy |", "|---|---|---|---|"]
            for b in s["calibration"]:
                md.append(f"| {b['range']} | {b['n']} | {pct(b['mean_confidence'])} | {pct(b['accuracy'])} |")
        md.append("")

    md += ["## Notes", "",
           "- Failed rows (API/network errors) are excluded from the metrics and counted in the Failed column.",
           "- Predicted `Not Checkable` is scored as `Unverified`.",
           "- Check the retrieval-leakage setting above before comparing runs."]
    return "\n".join(md)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--format", choices=["jsonl", "liar"], default="jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--modes", nargs="+", default=["baseline", "rag", "full"], choices=["baseline", "rag", "full"])
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--exclude-domain", action="append", default=[])
    ap.add_argument("--out", default="eval/reports")
    a = ap.parse_args()

    rows = datasets.load_liar(a.data) if a.format == "liar" else datasets.load_jsonl(a.data)
    rows = datasets.sample(rows, a.limit)
    exclude = tuple(a.exclude_domain)

    runs = {m: await run_mode(m, rows, a.concurrency, exclude) for m in a.modes}

    from app.config import get_settings
    meta = {"when": datetime.now().strftime("%Y-%m-%d %H:%M"), "data": a.data, "n": len(rows),
            "model": get_settings().anthropic_model, "exclude": list(exclude)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"run-{stamp}.json").write_text(json.dumps({"meta": meta, "runs": runs}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"report-{stamp}.md").write_text(render(runs, meta), encoding="utf-8")
    print(f"\nWrote {out}/report-{stamp}.md")


if __name__ == "__main__":
    asyncio.run(main())
