"""Map the many ways fact-checkers word a rating onto our four verdicts. Returns "" when unknown."""
import re

_UNVERIFIED = [r"unverified", r"unproven", r"no evidence", r"cannot be (verified|confirmed)", r"not (yet )?(verified|confirmed)",
               r"unclear", r"inconclusive", r"insufficient", r"अपुष्ट", r"ధృవీకరించ"]
_MISLEADING = [r"mislead", r"partly", r"partially", r"half[- ]?true", r"mixture", r"missing context", r"out of context",
               r"exaggerat", r"mostly false", r"barely true", r"distort", r"manipulated", r"altered", r"भ्रामक", r"తప్పుదోవ"]
_FALSE = [r"\bfalse\b", r"\bfake\b", r"\bfabricat", r"pants on fire", r"\bincorrect\b", r"\bhoax", r"\bfraud", r"\bscam\b",
          r"\bnot true\b", r"\buntrue\b", r"\bbogus\b", r"\bwrong\b", r"\bdebunked", r"झूठ", r"फर्जी", r"फ़र्ज़ी", r"गलत",
          r"అబద్ధం", r"తప్పు", r"నకిలీ"]
_TRUE = [r"\btrue\b", r"\bcorrect\b", r"\baccurate\b", r"\bgenuine\b", r"\bauthentic\b", r"\blegit", r"सच", r"सही", r"నిజం"]
_NEGATION_HI = re.compile(r"नहीं|नही")

_GROUPS = [("Unverified", _UNVERIFIED), ("Misleading", _MISLEADING), ("False", _FALSE), ("True", _TRUE)]
_COMPILED = [(label, [re.compile(p, re.I) for p in pats]) for label, pats in _GROUPS]


def normalize_rating(text: str | None) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    for label, pats in _COMPILED:       # order matters: "mostly false" is Misleading, "not true" is False
        if any(p.search(t) for p in pats):
            if label == "True" and _NEGATION_HI.search(t):
                return "False"
            return label
    return ""
