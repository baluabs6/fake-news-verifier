"""Reply-ready debunk text in English, Hindi and Telugu (template-based, no LLM).
Have a native speaker review the Hindi/Telugu wording before you ship it."""

TEXT = {
    "en": {
        "label": "Fact-check", "source": "Source", "full": "Full result",
        "note": "This is an evidence-based assessment.",
        "verdict": {"True": "True", "False": "False", "Misleading": "Misleading",
                    "Unverified": "Could not be verified", "Not Checkable": "Not a checkable claim"},
    },
    "hi": {
        "label": "फ़ैक्ट-चेक", "source": "स्रोत", "full": "पूरा नतीजा",
        "note": "यह सबूतों पर आधारित आकलन है।",
        "verdict": {"True": "सही", "False": "झूठ", "Misleading": "भ्रामक",
                    "Unverified": "पुष्टि नहीं हो सकी", "Not Checkable": "जाँचने योग्य दावा नहीं"},
    },
    "te": {
        "label": "ఫ్యాక్ట్ చెక్", "source": "మూలం", "full": "పూర్తి ఫలితం",
        "note": "ఇది ఆధారాల ఆధారంగా చేసిన అంచనా.",
        "verdict": {"True": "నిజం", "False": "అబద్ధం", "Misleading": "తప్పుదోవ పట్టించేది",
                    "Unverified": "ధృవీకరించలేకపోయాం", "Not Checkable": "తనిఖీ చేయదగిన అంశం కాదు"},
    },
}


def build_card(result: dict, link: str, lang: str = "en") -> str:
    t = TEXT.get(lang, TEXT["en"])
    word = t["verdict"].get(result.get("verdict", ""), result.get("verdict", ""))
    lines = [f"{t['label']}: {word}"]
    if result.get("summary"):
        lines.append(result["summary"])
    evidence = result.get("evidence", {})
    for claim in result.get("claims", []):
        for cid in claim.get("citations", []):
            if cid in evidence:
                lines.append(f"{t['source']}: {evidence[cid]['url']}")
                break
        else:
            continue
        break
    lines.append(f"{t['full']}: {link}")
    lines.append(t["note"])
    return "\n".join(lines)
