"""The unified fabric: one durable store behind both knowledge and execution.

Knowledge units, graph edges, capabilities, an append-only event log, a
guardian response cache and a failure memo all live in one SQLite file. A
single connection guarded by a re-entrant lock keeps it usable from the API
thread pool without handing out connections.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .models import Capability, KnowledgeUnit, Provenance, utcnow
from .ranking import BM25Index, bm25_scores, reciprocal_rank_fusion
from .semantic import SemanticIndex
from .vectors import cosine, embed, embed_query

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    license TEXT NOT NULL,
    confidence REAL NOT NULL,
    concepts TEXT NOT NULL,
    tags TEXT NOT NULL,
    embedding TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    src TEXT NOT NULL,
    rel TEXT NOT NULL,
    dst TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (src, rel, dst)
);
CREATE TABLE IF NOT EXISTS capabilities (
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    description TEXT NOT NULL,
    inputs TEXT NOT NULL,
    outputs TEXT NOT NULL,
    kind TEXT NOT NULL,
    entry TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance TEXT NOT NULL,
    spec TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (name, version)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guardian_cache (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS failure_memo (
    sig TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    count INTEGER NOT NULL,
    last_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class FabricStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self._lock = threading.RLock()
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._knowledge_revision = 0
        self._bm25_revision = -1
        self._bm25_index: BM25Index | None = None
        self._semantic_revision = -1
        self._semantic_index: SemanticIndex | None = None

    # -- lifecycle -------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- settings --------------------------------------------------------
    def get_setting(self, key: str) -> Any | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else None

    def set_setting(self, key: str, value: Any, updated_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, json.dumps(value), updated_at),
            )
            self._conn.commit()

    def delete_setting(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM settings WHERE key=?", (key,))
            self._conn.commit()

    def all_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value FROM settings ORDER BY key"
            ).fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    # -- knowledge -------------------------------------------------------
    def upsert_knowledge(self, unit: KnowledgeUnit) -> KnowledgeUnit:
        if not unit.embedding:
            unit.embedding = embed(unit.searchable_text())
        with self._lock:
            self._conn.execute(
                """INSERT INTO knowledge
                   (id, title, summary, source, url, retrieved_at, license,
                    confidence, concepts, tags, embedding, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, summary=excluded.summary,
                     source=excluded.source, url=excluded.url,
                     retrieved_at=excluded.retrieved_at,
                     license=excluded.license, confidence=excluded.confidence,
                     concepts=excluded.concepts, tags=excluded.tags,
                     embedding=excluded.embedding""",
                (
                    unit.id, unit.title, unit.summary, unit.provenance.source,
                    unit.provenance.url, unit.provenance.retrieved_at,
                    unit.provenance.license, unit.provenance.confidence,
                    json.dumps(list(unit.concepts)), json.dumps(list(unit.tags)),
                    json.dumps(unit.embedding), unit.created_at,
                ),
            )
            self._conn.commit()
            self._knowledge_revision += 1
        return unit

    def get_knowledge(self, unit_id: str) -> KnowledgeUnit | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM knowledge WHERE id=?", (unit_id,)
            ).fetchone()
        return _row_to_unit(row) if row else None

    def retrieval_index_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._knowledge_revision,
                "cached_revision": self._bm25_revision,
                "cached": self._bm25_index is not None
                and self._bm25_revision == self._knowledge_revision,
                "documents": len(self._bm25_index.ids) if self._bm25_index else 0,
                "semantic_cached": self._semantic_index is not None
                and self._semantic_revision == self._knowledge_revision,
                "semantic_documents": len(self._semantic_index.ids)
                if self._semantic_index
                else 0,
            }

    def _bm25_scores(self, query: str, units: list[KnowledgeUnit]) -> dict[str, float]:
        with self._lock:
            if self._bm25_index is None or self._bm25_revision != self._knowledge_revision:
                self._bm25_index = BM25Index(
                    {unit.id: unit.searchable_text() for unit in units}
                )
                self._bm25_revision = self._knowledge_revision
            index = self._bm25_index
        return index.scores(query)

    def _semantic_scores(self, query: str, units: list[KnowledgeUnit]) -> dict[str, float]:
        with self._lock:
            if self._semantic_index is None or self._semantic_revision != self._knowledge_revision:
                self._semantic_index = SemanticIndex(
                    {unit.id: unit.searchable_text() for unit in units}
                )
                self._semantic_revision = self._knowledge_revision
            index = self._semantic_index
        return index.scores(query)

    def search_knowledge(
        self,
        query: str,
        k: int = 5,
        qvec=None,
        mode: str = "vector",
    ) -> list[tuple[KnowledgeUnit, float]]:
        """Rank knowledge by vector, BM25, semantic, or fused hybrid retrieval.

        ``vector`` preserves the historical score (embedding + authority +
        recency). ``bm25`` ranks exact terms. ``semantic`` uses corpus-derived
        PPMI random-index vectors. ``hybrid`` fuses vector and BM25 ranked
        lists with reciprocal rank fusion; its score is an RRF score, not a
        probability.
        """
        mode = (mode or "vector").lower()
        if mode not in {"vector", "bm25", "hybrid", "semantic"}:
            raise ValueError("mode must be vector, bm25, hybrid, or semantic")
        if qvec is None and mode in {"vector", "hybrid"}:
            qvec = embed_query(query)
        with self._lock:
            rows = self._conn.execute("SELECT * FROM knowledge").fetchall()
        units = [_row_to_unit(row) for row in rows]

        def vector_rank() -> list[tuple[KnowledgeUnit, float]]:
            scored = []
            for unit in units:
                lexical = cosine(qvec, unit.embedding)
                # Authority and recency break ties that pure lexical overlap cannot.
                score = (
                    0.75 * lexical
                    + 0.15 * unit.provenance.confidence
                    + 0.10 * _recency_factor(unit.provenance.retrieved_at)
                )
                scored.append((unit, score))
            scored.sort(key=lambda pair: (-pair[1], pair[0].id))
            return scored

        if mode == "vector":
            return vector_rank()[:k]
        if mode == "semantic":
            semantic_scores = self._semantic_scores(query, units)
            by_id = {unit.id: unit for unit in units}
            ranked = sorted(
                ((by_id[item], score) for item, score in semantic_scores.items()),
                key=lambda pair: (-pair[1], pair[0].id),
            )
            return ranked[:k]

        lexical_scores = self._bm25_scores(query, units)
        by_id = {unit.id: unit for unit in units}
        lexical = sorted(
            ((by_id[item], score) for item, score in lexical_scores.items()),
            key=lambda pair: (-pair[1], pair[0].id),
        )
        if mode == "bm25":
            return lexical[:k]

        vector = vector_rank()
        fused = reciprocal_rank_fusion(
            [[unit.id for unit, _ in vector], [unit.id for unit, _ in lexical]]
        )
        ranked = sorted(
            ((by_id[unit_id], score) for unit_id, score in fused.items()),
            key=lambda pair: (-pair[1], pair[0].id),
        )
        return ranked[:k]

    def graph(self, node: str, rel: str | None = None, depth: int = 1) -> dict[str, list]:
        seen = {node}
        edges: set[tuple[str, str, str]] = set()
        frontier = {node}
        for _ in range(max(1, depth)):
            nxt: set[str] = set()
            for current in frontier:
                for src, relation, dst in self.neighbors(current, rel):
                    edges.add((src, relation, dst))
                    nxt.add(src)
                    nxt.add(dst)
            frontier = nxt - seen
            seen |= nxt
        return {"nodes": sorted(seen), "edges": [list(e) for e in sorted(edges)]}

    def list_knowledge(self, limit: int = 50) -> list[KnowledgeUnit]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM knowledge ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_unit(row) for row in rows]

    def count_knowledge(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]

    # -- graph -----------------------------------------------------------
    def add_edge(self, src: str, rel: str, dst: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO edges (src, rel, dst, created_at) VALUES (?,?,?,?)",
                (src, rel, dst, utcnow()),
            )
            self._conn.commit()

    def neighbors(self, node: str, rel: str | None = None) -> list[tuple[str, str, str]]:
        with self._lock:
            if rel is None:
                rows = self._conn.execute(
                    "SELECT src, rel, dst FROM edges WHERE src=? OR dst=? ORDER BY src, rel, dst",
                    (node, node),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT src, rel, dst FROM edges WHERE rel=? AND (src=? OR dst=?) "
                    "ORDER BY src, dst",
                    (rel, node, node),
                ).fetchall()
        return [(r["src"], r["rel"], r["dst"]) for r in rows]

    # -- capabilities ----------------------------------------------------
    def save_capability(self, cap: Capability) -> Capability:
        prov = cap.provenance or Provenance(source="builtin")
        with self._lock:
            self._conn.execute(
                """INSERT INTO capabilities
                   (name, version, description, inputs, outputs, kind, entry,
                    status, provenance, spec, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(name, version) DO UPDATE SET
                     description=excluded.description, inputs=excluded.inputs,
                     outputs=excluded.outputs, kind=excluded.kind,
                     entry=excluded.entry, status=excluded.status,
                     provenance=excluded.provenance, spec=excluded.spec""",
                (
                    cap.name, cap.version, cap.description,
                    json.dumps(list(cap.inputs)), json.dumps(list(cap.outputs)),
                    cap.kind, cap.entry, cap.status,
                    json.dumps(_prov_to_dict(prov)), json.dumps(cap.spec),
                    cap.created_at,
                ),
            )
            self._conn.commit()
        return cap

    def get_capability(self, name: str, version: int | None = None) -> Capability | None:
        with self._lock:
            if version is None:
                row = self._conn.execute(
                    "SELECT * FROM capabilities WHERE name=? ORDER BY version DESC LIMIT 1",
                    (name,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT * FROM capabilities WHERE name=? AND version=?",
                    (name, version),
                ).fetchone()
        return _row_to_cap(row) if row else None

    def list_capabilities(self, status: str | None = None) -> list[Capability]:
        with self._lock:
            if status is None:
                rows = self._conn.execute(
                    "SELECT * FROM capabilities ORDER BY name, version"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM capabilities WHERE status=? ORDER BY name, version",
                    (status,),
                ).fetchall()
        return [_row_to_cap(r) for r in rows]

    def set_capability_status(self, name: str, version: int, status: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE capabilities SET status=? WHERE name=? AND version=?",
                (status, name, version),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def next_version(self, name: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(version) FROM capabilities WHERE name=?", (name,)
            ).fetchone()
        return (row[0] or 0) + 1

    # -- event log -------------------------------------------------------
    def record_event(self, kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, kind, payload) VALUES (?,?,?)",
                (utcnow(), kind, json.dumps(payload, default=str)),
            )
            self._conn.commit()

    def list_events(self, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if kind is None:
                rows = self._conn.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM events WHERE kind=? ORDER BY id DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
        return [
            {"id": r["id"], "ts": r["ts"], "kind": r["kind"], "payload": json.loads(r["payload"])}
            for r in rows
        ]

    # -- guardian cache --------------------------------------------------
    def cache_get(self, key: str, ttl: float) -> Any | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, fetched_at FROM guardian_cache WHERE key=?", (key,)
            ).fetchone()
        if not row:
            return None
        if time.time() - row["fetched_at"] > ttl:
            return None
        return json.loads(row["payload"])

    def cache_set(self, key: str, payload: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO guardian_cache (key, payload, fetched_at) VALUES (?,?,?)",
                (key, json.dumps(payload, default=str), time.time()),
            )
            self._conn.commit()

    # -- failure memo ----------------------------------------------------
    def memo_record(self, sig: str, reason: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT count FROM failure_memo WHERE sig=?", (sig,)
            ).fetchone()
            count = (row["count"] if row else 0) + 1
            self._conn.execute(
                "INSERT OR REPLACE INTO failure_memo (sig, reason, count, last_ts) "
                "VALUES (?,?,?,?)",
                (sig, reason, count, utcnow()),
            )
            self._conn.commit()

    def memo_seen(self, sig: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM failure_memo WHERE sig=?", (sig,)
            ).fetchone()
        return row is not None

    def memo_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM failure_memo ORDER BY last_ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def _recency_factor(timestamp: str) -> float:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - parsed).days
    if age_days <= 365:
        return 1.0
    if age_days <= 1095:
        return 0.5
    return 0.0


def _prov_to_dict(prov: Provenance) -> dict[str, Any]:
    return {
        "source": prov.source,
        "url": prov.url,
        "retrieved_at": prov.retrieved_at,
        "license": prov.license,
        "confidence": prov.confidence,
    }


def _row_to_unit(row: sqlite3.Row) -> KnowledgeUnit:
    return KnowledgeUnit(
        id=row["id"],
        title=row["title"],
        summary=row["summary"],
        provenance=Provenance(
            source=row["source"],
            url=row["url"],
            retrieved_at=row["retrieved_at"],
            license=row["license"],
            confidence=row["confidence"],
        ),
        concepts=tuple(json.loads(row["concepts"])),
        tags=tuple(json.loads(row["tags"])),
        embedding=json.loads(row["embedding"]),
        created_at=row["created_at"],
    )


def _row_to_cap(row: sqlite3.Row) -> Capability:
    prov = json.loads(row["provenance"])
    return Capability(
        name=row["name"],
        version=row["version"],
        description=row["description"],
        inputs=tuple(json.loads(row["inputs"])),
        outputs=tuple(json.loads(row["outputs"])),
        kind=row["kind"],
        entry=row["entry"],
        status=row["status"],
        provenance=Provenance(**prov),
        spec=json.loads(row["spec"]),
        created_at=row["created_at"],
    )
