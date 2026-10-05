"""Redact personal identifiers before text is stored or sent to the model."""
import re

# Order matters: more specific patterns first.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("UPI", re.compile(r"\b[\w.-]{2,}@(?:ybl|ibl|axl|okaxis|oksbi|okhdfcbank|okicici|paytm|apl|upi|axisbank|sbi|icici|hdfcbank)\b", re.I)),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
]


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for label, pat in PATTERNS:
        text, n = pat.subn(f"[{label}]", text)
        if n:
            counts[label] = counts.get(label, 0) + n
    return text, counts
