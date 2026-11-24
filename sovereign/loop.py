"""A bounded continuous-evolution loop.

Each tick consults a topic, absorbs what it finds, and (optionally) runs one
measured optimization. This is a scheduler with a stop button, not autonomy:
it does exactly these steps and nothing else.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from .absorption import absorb
from .models import utcnow
from .optimizer import Optimizer

DEFAULT_TOPICS = [
    "retrieval augmented generation",
    "program synthesis",
    "sqlite full text search",
    "deterministic embeddings",
    "fault tolerant planning",
]


class EvolutionLoop:
    def __init__(
        self,
        engine,
        *,
        interval_s: float = 60.0,
        topics: list[str] | None = None,
        sources: list[str] | None = None,
        optimize: bool = True,
    ) -> None:
        self.engine = engine
        self.interval_s = max(0.05, float(interval_s))
        self.topics = list(topics or DEFAULT_TOPICS)
        self.sources = sources
        self.optimize_enabled = optimize
        self.optimizer = Optimizer(engine.registry)
        self.generation = 0
        self.history: deque[dict[str, Any]] = deque(maxlen=20)
        self.last: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.started_at: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def tick(self) -> dict[str, Any]:
        with self._lock:
            topic = self.topics[self.generation % len(self.topics)]
        consultation = self.engine.guardians.consult(
            topic, limit=2, sources=self.sources, deadline_s=8.0
        )
        absorbed = absorb(self.engine.store, consultation.units)
        optimization = None
        if self.optimize_enabled:
            names = [n for n in ("tokens.count", "counts.summarize") if self.engine.registry.active(n)]
            if names:
                optimization = self.optimizer.optimize(names[self.generation % len(names)], repeats=5)
        with self._lock:
            self.generation += 1
            summary = {
                "generation": self.generation,
                "topic": topic,
                "units": len(consultation.units),
                "absorbed": absorbed,
                "sources": consultation.sources,
                "optimization": optimization,
                "at": utcnow(),
            }
            self.last = summary
            self.history.append(summary)
        self.engine.store.record_event("loop.tick", summary)
        return summary

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.engine.store.record_event("loop.error", {"error": self.last_error})
            self._stop.wait(self.interval_s)

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="sovereign-loop", daemon=True)
            self.started_at = utcnow()
            self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)
        self._thread = None
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._thread is not None and self._thread.is_alive()),
            "generation": self.generation,
            "interval_s": self.interval_s,
            "topics": self.topics,
            "started_at": self.started_at,
            "last": self.last,
            "last_error": self.last_error,
            "history": list(self.history),
        }
