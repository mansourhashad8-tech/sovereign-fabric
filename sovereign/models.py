"""Value objects for the cognitive-executive fabric.

Two invariants are encoded here and enforced by the rest of the package:

1. Knowledge without provenance is not knowledge. Every KnowledgeUnit and
   Capability carries a Provenance record naming where it came from.
2. A claim without evidence is a hypothesis, not a fact. Evidence is a
   first-class object, and ValidationReport refuses to pass a claim that
   has none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Provenance:
    source: str
    url: str = ""
    retrieved_at: str = field(default_factory=utcnow)
    license: str = ""
    confidence: float = 0.5


@dataclass
class KnowledgeUnit:
    id: str
    title: str
    summary: str
    provenance: Provenance
    concepts: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    embedding: list[float] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow)

    def searchable_text(self) -> str:
        return " ".join((self.title, self.summary, *self.concepts, *self.tags))


@dataclass
class Capability:
    name: str
    description: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    kind: str = "builtin"  # builtin | synthesized
    entry: str = ""  # "module:function" for builtin, source code for synthesized
    version: int = 1
    status: str = "admitted"  # admitted | quarantined | rolled_back
    provenance: Provenance | None = None
    spec: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow)

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class Evidence:
    kind: str
    detail: str
    ref: str = ""


@dataclass
class ValidationReport:
    subject: str
    scores: dict[str, float]
    passed: bool
    failures: list[str] = field(default_factory=list)
    overclaims: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PlanStep:
    capability: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]
    version: int = 1


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep]
    solved: bool
    explored: int = 0
    reason: str = ""
