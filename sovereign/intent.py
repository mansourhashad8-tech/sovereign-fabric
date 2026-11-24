"""Keyword intent mapping for Arabic and English requests.

This is a router, not a language model. It picks the earliest matching keyword
and hands the rest to the planner. When nothing matches it defaults to a
markdown report and says `matched: null`.
"""

from __future__ import annotations

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("summary", ("لخص", "ملخص", "خلاصة", "summarize", "summary")),
    ("counts", ("عدد", "تكرار", "إحصاء", "احص", "count", "frequency")),
    ("tokens", ("كلمات", "توكن", "قسّم", "قسم", "tokenize", "tokens")),
    ("markdown", ("تقرير", "اكتب", "report", "markdown", "brief")),
]


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
        _, _, goal, word = min(matches)
    else:
        goal, word = "markdown", ""
    return {
        "goal_type": goal,
        "matched": word or None,
        "request": text,
        "text": payload_text(text),
    }
