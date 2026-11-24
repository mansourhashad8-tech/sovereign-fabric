"""Native capabilities: pure transforms over a payload dict.

Convention: every capability takes a payload dict and returns a dict. The
built-ins below form a chain (text -> tokens -> counts -> report -> markdown)
so the planner has real multi-step work to find.
"""

from __future__ import annotations

from typing import Any

from .arabic import split_sentences, tokenize_text


def tokenize(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("value", ""))
    return {"value": tokenize_text(text)}


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
    sentences = split_sentences(str(payload.get("value", "")))
    return {"value": sentences[0] if sentences else ""}


NATIVE: dict[str, Any] = {
    "text.tokenize": tokenize,
    "tokens.count": count_tokens,
    "counts.summarize": summarize_counts,
    "report.format": format_report,
    "text.summarize": extractive_summary,
}


# Equivalent implementations, used by the measured self-optimizer.
import heapq as _heapq
import re as _re
from collections import Counter as _Counter

_WHITESPACE = _re.compile(r"\S+")
_SENTENCE_END = _re.compile(r"[.!?]")


def tokenize_regex(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": tokenize_text(str(payload.get("value", "")))}


def count_tokens_counter(payload: dict[str, Any]) -> dict[str, Any]:
    tokens = payload.get("value") or []
    return {"value": dict(_Counter(map(str, tokens)))}


def summarize_counts_heap(payload: dict[str, Any]) -> dict[str, Any]:
    counts = payload.get("value") or {}
    top = _heapq.nsmallest(5, counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"value": {"top": [list(pair) for pair in top], "distinct": len(counts)}}


def format_report_generator(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("value") or {}
    lines = [f"- {key}: {value}" for key, value in report.get("top", [])]
    return {"value": "\n".join(lines) if lines else "(empty)"}


def extractive_summary_regex(payload: dict[str, Any]) -> dict[str, Any]:
    sentences = [s.strip() for s in _SENTENCE_END.split(str(payload.get("value", ""))) if s.strip()]
    return {"value": sentences[0] if sentences else ""}


NATIVE.update(
    {
        "text.tokenize.regex": tokenize_regex,
        "tokens.count.counter": count_tokens_counter,
        "counts.summarize.heap": summarize_counts_heap,
        "report.format.generator": format_report_generator,
        "text.summarize.regex": extractive_summary_regex,
    }
)
