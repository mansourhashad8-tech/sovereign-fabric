"""Privacy-preserving collective lessons, exported manually.

This is not federated learning and it is not a global brain. It is a strict,
local exchange format: anonymized lessons can be exported as JSON and imported
by another instance. No client identifiers, IPs, queries, payloads, prompts,
knowledge text, keys, or timestamps are exported. Imported lessons are data;
they do not become capabilities.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .store import FabricStore

SCHEMA = "sovereign-collective/v1"
LESSON_SCHEMA = "sovereign-lesson/v1"
MAX_LESSONS = 500
_SAFE = re.compile(r"^[A-Za-z0-9._/#-]{0,80}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{16}$")
_ALLOWED = {
    "schema",
    "kind",
    "category",
    "route_class",
    "score_bucket",
    "action",
    "count",
    "fingerprint",
}
_BUCKETS = {"low", "medium", "high"}


def _bucket(score: float) -> str:
    if score >= 3.0:
        return "high"
    if score >= 1.5:
        return "medium"
    return "low"


def _fingerprint(lesson: dict[str, Any]) -> str:
    raw = "|".join(
        str(lesson.get(key, ""))
        for key in ("kind", "category", "route_class", "score_bucket", "action")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _lesson(kind: str, category: str, action: str, **extra: Any) -> dict[str, Any]:
    lesson = {
        "schema": LESSON_SCHEMA,
        "kind": str(kind)[:32],
        "category": str(category)[:48],
        "route_class": str(extra.get("route_class", ""))[:80],
        "score_bucket": str(extra.get("score_bucket", "low")),
        "action": str(action)[:32],
        "count": max(1, int(extra.get("count", 1))),
    }
    lesson["fingerprint"] = _fingerprint(lesson)
    return lesson


def lesson_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(event.get("kind", ""))
    payload = event.get("payload") or {}
    if kind == "immune.incident":
        return _lesson(
            "immune",
            payload.get("category", "anomaly"),
            payload.get("action", "quarantine"),
            route_class=payload.get("route_class", ""),
            score_bucket=_bucket(float(payload.get("score", 0))),
        )
    if kind == "self_repair":
        actions = payload.get("actions") or []
        return _lesson(
            "repair",
            "builtin_entry",
            "restore" if actions else "clean",
            count=max(1, len(actions)),
        )
    if kind == "capability.optimized":
        speedup = float(payload.get("speedup", 0) or 0)
        return _lesson(
            "optimization",
            "capability",
            "optimize",
            score_bucket=_bucket(speedup),
            count=1,
        )
    if kind == "evolution":
        return _lesson(
            "evolution",
            "cycle",
            "pass" if payload.get("ok") else "fail",
            count=max(1, int(payload.get("attempts", 1) or 1)),
        )
    if kind == "feedback":
        rating = int(payload.get("rating", 0) or 0)
        return _lesson(
            "feedback",
            "capability",
            "positive" if rating > 0 else "negative" if rating < 0 else "neutral",
            count=1,
        )
    if kind == "collective.lesson":
        valid, lesson = validate_lesson(payload)
        return lesson if valid else None
    return None


def validate_lesson(lesson: Any) -> tuple[bool, dict[str, Any] | str]:
    if not isinstance(lesson, dict):
        return False, "lesson must be an object"
    unknown = set(lesson) - _ALLOWED
    if unknown:
        return False, f"unknown fields: {sorted(unknown)}"
    if lesson.get("schema") != LESSON_SCHEMA:
        return False, "wrong lesson schema"
    kind = lesson.get("kind")
    category = lesson.get("category")
    route_class = lesson.get("route_class", "")
    action = lesson.get("action")
    bucket = lesson.get("score_bucket")
    count = lesson.get("count")
    fingerprint = lesson.get("fingerprint")
    if not isinstance(kind, str) or not kind or len(kind) > 32:
        return False, "invalid kind"
    if not isinstance(category, str) or not category or len(category) > 48:
        return False, "invalid category"
    if not isinstance(route_class, str) or not _SAFE.match(route_class):
        return False, "invalid route_class"
    if not isinstance(action, str) or not action or len(action) > 32:
        return False, "invalid action"
    if bucket not in _BUCKETS:
        return False, "invalid score_bucket"
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1_000_000:
        return False, "invalid count"
    if not isinstance(fingerprint, str) or not _FINGERPRINT.match(fingerprint):
        return False, "invalid fingerprint"
    expected = _fingerprint(lesson)
    if fingerprint != expected:
        return False, "fingerprint does not match the lesson"
    return True, {**lesson}


def collect_lessons(store: FabricStore, limit: int = 2_000) -> list[dict[str, Any]]:
    lessons: dict[str, dict[str, Any]] = {}
    for event in store.list_events(None, limit):
        lesson = lesson_from_event(event)
        if lesson is None:
            continue
        current = lessons.get(lesson["fingerprint"])
        if current is None:
            lessons[lesson["fingerprint"]] = lesson
        else:
            current["count"] = min(1_000_000, int(current["count"]) + int(lesson["count"]))
    return sorted(lessons.values(), key=lambda item: item["fingerprint"])


def export_bundle(store: FabricStore, limit: int = MAX_LESSONS) -> dict[str, Any]:
    lessons = collect_lessons(store)[: max(1, min(int(limit), MAX_LESSONS))]
    kinds: dict[str, int] = {}
    for lesson in lessons:
        kinds[lesson["kind"]] = kinds.get(lesson["kind"], 0) + 1
    return {
        "schema": SCHEMA,
        "exchange_mode": "manual export/import; no network transport",
        "federated_learning": False,
        "model_weights_shared": False,
        "privacy": (
            "no client identifiers, IPs, queries, payloads, prompts, knowledge "
            "text, keys, or timestamps"
        ),
        "lessons": lessons,
        "count": len(lessons),
        "by_kind": kinds,
    }


def import_bundle(store: FabricStore, bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        return {"ok": False, "error": "bundle must be an object", "accepted": 0}
    if bundle.get("schema") != SCHEMA:
        return {"ok": False, "error": "wrong bundle schema", "accepted": 0}
    lessons = bundle.get("lessons")
    if not isinstance(lessons, list) or len(lessons) > MAX_LESSONS:
        return {
            "ok": False,
            "error": f"lessons must be a list of at most {MAX_LESSONS}",
            "accepted": 0,
        }
    existing = {lesson["fingerprint"] for lesson in collect_lessons(store)}
    accepted: list[str] = []
    duplicates: list[str] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(lessons):
        valid, result = validate_lesson(raw)
        if not valid:
            rejected.append({"index": index, "reason": result})
            continue
        fingerprint = result["fingerprint"]
        if fingerprint in existing:
            duplicates.append(fingerprint)
            continue
        store.record_event("collective.lesson", result)
        existing.add(fingerprint)
        accepted.append(fingerprint)
    return {
        "ok": not rejected,
        "accepted": len(accepted),
        "duplicates": len(duplicates),
        "rejected": rejected,
        "fingerprints": accepted,
    }


def collective_status(store: FabricStore) -> dict[str, Any]:
    lessons = collect_lessons(store)
    return {
        "schema": SCHEMA,
        "lessons": len(lessons),
        "by_kind": {
            kind: sum(1 for lesson in lessons if lesson["kind"] == kind)
            for kind in sorted({lesson["kind"] for lesson in lessons})
        },
        "exchange_mode": "manual export/import; no network transport",
        "federated_learning": False,
        "privacy": "anonymized lessons only; no raw data or identifiers",
    }
