"""Keyword intent mapping for Arabic and English requests.

This is a router, not a language model. It picks the earliest matching keyword
and hands the rest to the planner. When nothing matches it defaults to a
markdown report and says `matched: null`.
"""

from __future__ import annotations

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("keywords", ("كلمات مفتاحية", "مفتاحية", "keywords", "keyphrases")),
    ("stats", ("إحصاءات", "احصائيات", "stats", "statistics")),
    ("language", ("لغة النص", "لغة", "language", "langdetect")),
    ("sentences", ("جمل", "sentences")),
    ("redact", ("احجب", "حجب", "redact", "redaction")),
    ("entities", ("كيانات", "كيان", "entities")),
    ("hash", ("تجزئة", "هاش", "sha256", "hash")),
    ("base64", ("base64", "بيس64")),
    ("similarity", ("تشابه", "similarity")),
    ("math", ("احسب", "حساب", "calculate", "math")),
    ("date", ("تاريخ", "date")),
    ("url", ("رابط", "url", "link")),
    ("json", ("json", "جيسون")),
    ("csv", ("csv", "سي اس في")),
    ("toml", ("toml", "تومل")),
    ("ini", ("ini:", "ini file", "ملف ini", "إيني")),
    ("html", ("html", "اتش تي ام ال")),
    ("headings", ("عناوين", "headings", "markdown headings")),
    ("summary", ("لخص", "ملخص", "خلاصة", "summarize", "summary")),
    ("counts", ("عدد", "تكرار", "إحصاء", "احص", "count", "frequency")),
    ("tokens", ("كلمات", "توكن", "قسّم", "قسم", "tokenize", "tokens")),
    ("markdown", ("تقرير", "اكتب", "report", "markdown", "brief")),
]

_INITIAL = {
    "json": "json_text",
    "csv": "csv_text",
    "math": "expression",
    "date": "dates",
    "url": "url",
    "similarity": "text_pair",
    "html": "html_text",
    "toml": "toml_text",
    "ini": "ini_text",
}

_GOAL = {
    "stats": "text_stats",
    "redact": "redacted_text",
    "hash": "digest",
    "json": "json_pretty",
    "csv": "table",
    "math": "number",
    "date": "days",
    "url": "url_parts",
    "html": "text",
    "toml": "json_pretty",
    "ini": "json_pretty",
}


def payload_text(request: str) -> str:
    text = request.strip()
    if ":" in text:
        tail = text.split(":", 1)[1].strip()
        if tail:
            return tail
    return text


def parse_intent(request: str) -> dict[str, object]:
    text = request.strip()
    lowered = text.lower()
    matches: list[tuple[int, int, str, str]] = []
    for order, (goal, words) in enumerate(_RULES):
        for word in words:
            index = lowered.find(word)
            if index >= 0:
                matches.append((index, order, goal, word))
    if matches:
        _, _, raw_goal, word = min(matches)
    else:
        raw_goal, word = "markdown", ""
    goal = _GOAL.get(raw_goal, raw_goal)
    return {
        "goal_type": goal,
        "initial": _INITIAL.get(raw_goal, "text"),
        "matched": word or None,
        "request": text,
        "text": payload_text(text),
    }
