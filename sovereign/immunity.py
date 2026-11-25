"""Adaptive, in-process anomaly detection and short quarantine.

This is an online statistical detector, not deep learning. It learns a moving
latency baseline and per-client error/path-diversity statistics, adds fixed
signatures for common scan paths, and quarantines a client for a bounded time
when the score crosses a threshold. Client identifiers are hashed before they
reach the event log.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .store import FabricStore

MAX_CLIENTS = 10_000
MAX_PATHS = 200
SUSPICIOUS = (
    ".env",
    "../",
    "..%2f",
    "%2e%2e",
    "/etc/passwd",
    "/.git",
    "wp-admin",
    "phpmyadmin",
    "actuator",
    "/admin",
    "union%20",
    "select%20",
    "<script",
    "cmd=",
)
_NUMBERS = re.compile(r"\d+")
_KNOWN_ROUTES = {
    "health", "ready", "metrics", "diagnostics", "dashboard", "guardians",
    "consult", "absorb", "knowledge", "capabilities", "synthesize", "evolve",
    "curriculum", "redteam", "execute", "cache", "remote", "self", "properties",
    "security", "brief", "mastery", "verify_claim", "ask", "invoke", "pipeline",
    "feedback", "expert", "immunity", "collective", "autonomy", "evolution",
    "optimize", "loop", "report", "cycles", "failures", "validate", "acquire",
}


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    score: float
    reason: str = ""
    retry_after: int = 0


@dataclass
class ClientState:
    count: int = 0
    errors: int = 0
    hits: list[float] = field(default_factory=list)
    paths: set[str] = field(default_factory=set)
    score: float = 0.0
    quarantined_until: float = 0.0
    last_seen: float = 0.0


def _hash(client: str) -> str:
    return hashlib.sha256(client.encode("utf-8", "replace")).hexdigest()[:16]


def _route_class(path: str) -> str:
    clean = path.split("?", 1)[0]
    parts = [part for part in clean.split("/") if part]
    if not parts:
        return "/"
    first = _NUMBERS.sub("#", parts[0])[:40]
    if first.startswith(".") or first in _KNOWN_ROUTES:
        return f"/{first}"
    return "/other"


class ImmuneSystem:
    def __init__(
        self,
        store: FabricStore | None = None,
        *,
        threshold: float = 3.0,
        window_s: float = 60.0,
        quarantine_s: float = 60.0,
        min_samples: int = 8,
    ) -> None:
        self.store = store
        self.threshold = float(threshold)
        self.window_s = float(window_s)
        self.quarantine_s = float(quarantine_s)
        self.min_samples = max(1, int(min_samples))
        self._clients: dict[str, ClientState] = {}
        self._latency_ewma: float | None = None
        self._learned_paths: set[str] = set()
        self._lock = threading.Lock()
        self.observations = 0
        self.quarantines = 0

    def pre_check(self, client: str, path: str, now: float | None = None) -> Verdict:
        current = time.monotonic() if now is None else now
        with self._lock:
            state = self._clients.get(client)
            if state is None:
                return Verdict(True, 0.0)
            if state.quarantined_until > current:
                return Verdict(
                    False,
                    state.score,
                    "immune_quarantine",
                    max(1, math.ceil(state.quarantined_until - current)),
                )
            return Verdict(True, state.score)

    def observe(
        self,
        client: str,
        path: str,
        status: int,
        duration_s: float,
        method: str = "GET",
        now: float | None = None,
    ) -> dict[str, Any]:
        current = time.monotonic() if now is None else now
        route = _route_class(path)
        raw = path.lower()
        clean_path = path.split("?", 1)[0]
        path_hash = hashlib.sha256(clean_path.encode("utf-8", "replace")).hexdigest()[:16]
        learned = path_hash in self._learned_paths
        suspicious = any(token in raw for token in SUSPICIOUS)
        with self._lock:
            if len(self._clients) > MAX_CLIENTS:
                self._clients = {
                    key: value
                    for key, value in self._clients.items()
                    if value.quarantined_until > current or value.count > 2
                }
            state = self._clients.setdefault(client, ClientState())
            state.count += 1
            state.last_seen = current
            if status >= 400:
                state.errors += 1
            state.hits.append(current)
            cutoff = current - self.window_s
            while state.hits and state.hits[0] <= cutoff:
                state.hits.pop(0)
            if len(state.paths) < MAX_PATHS:
                state.paths.add(route)
            alpha = 0.2
            if self._latency_ewma is None:
                self._latency_ewma = max(0.0, duration_s)
                latency_z = 0.0
            else:
                self._latency_ewma = (1 - alpha) * self._latency_ewma + alpha * max(
                    0.0, duration_s
                )
                latency_z = abs(duration_s - self._latency_ewma) / max(
                    1e-6, self._latency_ewma
                )
            error_rate = (state.errors + 1) / (state.count + 5)
            unique_ratio = len(state.paths) / max(1, min(state.count, 25))
            score = (
                min(2.0, error_rate * 6)
                + min(1.2, max(0.0, unique_ratio - 0.5) * 2.4)
                + (2.5 if suspicious else 0.0)
                + (1.0 if learned else 0.0)
                + min(0.8, max(0.0, latency_z - 3.0) * 0.2)
            )
            state.score = round(score, 3)
            self.observations += 1
            trigger = score >= self.threshold and (
                suspicious or state.count >= self.min_samples
            )
            if trigger and state.quarantined_until <= current:
                state.quarantined_until = current + self.quarantine_s
                self.quarantines += 1
                if suspicious:
                    if len(self._learned_paths) >= 1_000:
                        self._learned_paths.clear()
                    self._learned_paths.add(path_hash)
                incident = {
                    "client_hash": _hash(client),
                    "category": "scan" if suspicious else "anomaly",
                    "route_class": route,
                    "method": method[:8],
                    "status": int(status),
                    "score": state.score,
                    "action": "quarantine",
                    "quarantine_s": self.quarantine_s,
                }
                if self.store is not None:
                    self.store.record_event("immune.incident", incident)
            return {
                "score": state.score,
                "quarantined": state.quarantined_until > current,
                "suspicious": suspicious,
                "route_class": route,
            }

    def status(self) -> dict[str, Any]:
        current = time.monotonic()
        with self._lock:
            active = [
                {
                    "client_hash": _hash(client),
                    "score": state.score,
                    "count": state.count,
                    "errors": state.errors,
                    "paths": len(state.paths),
                    "quarantined_for_s": max(
                        0, math.ceil(state.quarantined_until - current)
                    ),
                }
                for client, state in self._clients.items()
                if state.quarantined_until > current
            ]
            active.sort(key=lambda row: (-row["score"], row["client_hash"]))
            return {
                "mode": "online statistical anomaly detection (not deep learning)",
                "threshold": self.threshold,
                "window_s": self.window_s,
                "quarantine_s": self.quarantine_s,
                "min_samples": self.min_samples,
                "observations": self.observations,
                "clients": len(self._clients),
                "quarantined": len(active),
                "quarantines_total": self.quarantines,
                "learned_signatures": len(self._learned_paths),
                "latency_ewma_s": round(self._latency_ewma or 0.0, 6),
                "active": active[:10],
            }

    def incidents(self, limit: int = 50) -> list[dict[str, Any]]:
        if self.store is None:
            return []
        return self.store.list_events("immune.incident", limit)

    def scan(self) -> dict[str, Any]:
        report = self.status()
        report["incidents"] = self.incidents(20)
        return report

    def reset(self, clear_history: bool = False) -> dict[str, Any]:
        with self._lock:
            for state in self._clients.values():
                state.quarantined_until = 0.0
            if clear_history:
                self._clients.clear()
                self.observations = 0
                self.quarantines = 0
                self._latency_ewma = None
                self._learned_paths.clear()
        return self.status()
