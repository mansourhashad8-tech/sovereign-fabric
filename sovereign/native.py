"""Native capabilities: pure transforms over a payload dict.

Convention: every capability takes a payload dict and returns a dict. The
built-ins below form a chain (text -> tokens -> counts -> report -> markdown)
so the planner has real multi-step work to find.
"""

from __future__ import annotations

from typing import Any


def tokenize(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("value", ""))
    return {"value": text.split()}


def count_tokens(payload: dict[str, Any]) -> dict[str, Any]:
    tokens = payload.get("value") or []
    counts: dict[str, int] = {}
    for token in tokens:
        counts[str(token)] = counts.get(str(token), 0) + 1
    return {"value": counts}


def summarize_counts(payload: dict[str, Any]) -> dict[str, Any]:
    counts = payload.get("value") or {}
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {"value": {"top": [list(pair) for pair in top], "distinct": len(counts)}}


def format_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("value") or {}
    lines = [f"- {key}: {value}" for key, value in report.get("top", [])]
    return {"value": "\n".join(lines) if lines else "(empty)"}


def extractive_summary(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("value", ""))
    normalized = text.replace("!", ".").replace("?", ".")
    sentences = [s.strip() for s in normalized.split(".") if s.strip()]
    return {"value": sentences[0] if sentences else ""}


NATIVE: dict[str, Any] = {
    "text.tokenize": tokenize,
    "tokens.count": count_tokens,
    "counts.summarize": summarize_counts,
    "report.format": format_report,
    "text.summarize": extractive_summary,
}
