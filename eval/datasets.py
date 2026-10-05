"""Load labelled claims. Gold labels are always one of: True, False, Misleading, Unverified."""
import csv
import json
import random
from pathlib import Path

# Judgement call, state it in your report. LIAR has six PolitiFact labels.
LIAR_MAP = {
    "true": "True", "mostly-true": "True",
    "half-true": "Misleading",
    "barely-true": "False", "false": "False", "pants-fire": "False",
}


def load_jsonl(path: str) -> list[dict]:
    """Each line: {"claim": "...", "label": "True|False|Misleading|Unverified", "lang": "en" (optional)}"""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            assert r["label"] in {"True", "False", "Misleading", "Unverified"}, f"bad label: {r['label']}"
            rows.append(r)
    return rows


def load_liar(path: str) -> list[dict]:
    """LIAR train/valid/test .tsv: column 1 = label, column 2 = statement."""
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for rec in csv.reader(f, delimiter="\t"):
            if len(rec) > 2 and rec[1] in LIAR_MAP:
                rows.append({"claim": rec[2], "label": LIAR_MAP[rec[1]], "lang": "en", "raw_label": rec[1]})
    return rows


def sample(rows: list[dict], limit: int, seed: int = 7) -> list[dict]:
    if limit and limit < len(rows):
        rows = random.Random(seed).sample(rows, limit)  # reproducible subset
    return rows
