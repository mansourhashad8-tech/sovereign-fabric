"""Concrete guardians. Each one normalises a real public source into
KnowledgeUnits. Parsing is separated from transport so it can be tested
against recorded fixtures without a network.
"""

from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET

from ..models import KnowledgeUnit, Provenance, utcnow
from ..vectors import cosine, embed
from .base import HttpGuardian, quote

_ATOM = "{http://www.w3.org/2005/Atom}"
_TAG = re.compile(r"<[^>]+>")


def _plain(text: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", text or "")).split())


class ArxivGuardian(HttpGuardian):
    name = "arxiv"
    base_confidence = 0.7
    min_interval = 3.0  # arXiv asks clients to space requests by ~3s

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            "https://export.arxiv.org/api/query"
            f"?search_query=all:{quote(query)}&start=0&max_results={limit}"
        )
        root = ET.fromstring(self._get(url))
        units: list[KnowledgeUnit] = []
        for entry in root.findall(f"{_ATOM}entry"):
            title = entry.findtext(f"{_ATOM}title") or ""
            if not title.strip():
                continue
            summary = entry.findtext(f"{_ATOM}summary") or ""
            link = (entry.findtext(f"{_ATOM}id") or "").strip()
            published = (entry.findtext(f"{_ATOM}published") or "").strip()
            cats = tuple(
                c.attrib.get("term", "") for c in entry.findall(f"{_ATOM}category")
            )
            units.append(
                self._unit(
                    title=title,
                    summary=summary,
                    url=link,
                    concepts=tuple(c for c in cats if c),
                    tags=("paper", "arxiv"),
                    license="arXiv",
                    retrieved_at=published or None,
                )
            )
        return units[:limit]


def _openalex_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for idx in idxs:
            positions.append((idx, word))
    positions.sort()
    return " ".join(word for _, word in positions)


class OpenAlexGuardian(HttpGuardian):
    name = "openalex"
    base_confidence = 0.65
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            f"https://api.openalex.org/works?search={quote(query)}"
            f"&per-page={limit}&mailto=sovereign@example.org"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for work in data.get("results", []):
            title = work.get("title") or work.get("display_name") or ""
            if not title.strip():
                continue
            concepts = tuple(
                t.get("display_name", "")
                for t in (work.get("topics") or [])[:4]
                if t.get("display_name")
            )
            units.append(
                self._unit(
                    title=title,
                    summary=_openalex_abstract(work.get("abstract_inverted_index")),
                    url=work.get("id", ""),
                    concepts=concepts,
                    tags=("paper", "openalex"),
                    license="CC0",
                    retrieved_at=work.get("publication_date") or None,
                )
            )
        return units[:limit]


class GithubGuardian(HttpGuardian):
    name = "github"
    base_confidence = 0.55
    min_interval = 2.0

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            f"https://api.github.com/search/repositories?q={quote(query)}"
            f"&sort=stars&order=desc&per_page={limit}"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for item in data.get("items", []):
            name = item.get("full_name", "")
            if not name:
                continue
            stars = int(item.get("stargazers_count") or 0)
            confidence = min(0.92, 0.5 + math.log10(stars + 1) / 8)
            license_id = (item.get("license") or {}).get("spdx_id") or ""
            units.append(
                self._unit(
                    title=name,
                    summary=item.get("description") or "",
                    url=item.get("html_url", ""),
                    concepts=tuple(item.get("topics") or ()),
                    tags=("code", "github"),
                    confidence=confidence,
                    license=license_id,
                )
            )
        return units[:limit]


class HackerNewsGuardian(HttpGuardian):
    name = "hackernews"
    base_confidence = 0.45
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            f"https://hn.algolia.com/api/v1/search?query={quote(query)}"
            f"&tags=story&hitsPerPage={limit}"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for hit in data.get("hits", []):
            title = hit.get("title") or hit.get("story_title") or ""
            if not title.strip():
                continue
            points = int(hit.get("points") or 0)
            confidence = min(0.75, 0.35 + math.log10(points + 1) / 10)
            link = hit.get("url") or (
                f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            )
            units.append(
                self._unit(
                    title=title,
                    summary=hit.get("story_text") or "",
                    url=link,
                    tags=("discussion", "hackernews"),
                    confidence=confidence,
                    retrieved_at=hit.get("created_at") or None,
                )
            )
        return units[:limit]


class PyPIGuardian(HttpGuardian):
    name = "pypi"
    base_confidence = 0.6
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        # PyPI exposes no keyword-search JSON API; this is an exact-name lookup.
        try:
            data = json.loads(self._get(f"https://pypi.org/pypi/{quote(query)}/json"))
        except Exception:
            return []
        info = data.get("info", {})
        name = info.get("name") or query
        keywords = [k.strip() for k in (info.get("keywords") or "").split(",") if k.strip()]
        url = (
            info.get("project_url")
            or info.get("home_page")
            or f"https://pypi.org/project/{name}/"
        )
        return [
            self._unit(
                title=name,
                summary=info.get("summary") or "",
                url=url,
                concepts=tuple(keywords[:6]),
                tags=("package", "pypi"),
                confidence=0.7,
                license=info.get("license") or "",
            )
        ]


_TAG = re.compile(r"<[^>]+>")


class SemanticScholarGuardian(HttpGuardian):
    name = "semanticscholar"
    base_confidence = 0.65
    min_interval = 1.0

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={quote(query)}&limit={limit}"
            "&fields=title,abstract,url,year,venue,fieldsOfStudy"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for paper in data.get("data", []):
            title = paper.get("title") or ""
            if not title.strip():
                continue
            year = paper.get("year")
            retrieved = f"{year}-01-01T00:00:00+00:00" if year else None
            units.append(
                self._unit(
                    title=title,
                    summary=paper.get("abstract") or "",
                    url=paper.get("url") or "",
                    concepts=tuple(paper.get("fieldsOfStudy") or ()),
                    tags=("paper", "semanticscholar"),
                    retrieved_at=retrieved,
                )
            )
        return units[:limit]


class CrossrefGuardian(HttpGuardian):
    name = "crossref"
    base_confidence = 0.6
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            f"https://api.crossref.org/works?query={quote(query)}&rows={limit}"
            "&select=title,URL,abstract,issued,container-title,license"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for item in data.get("message", {}).get("items", []):
            titles = item.get("title") or [""]
            title = titles[0] if titles else ""
            if not title.strip():
                continue
            abstract = _TAG.sub(" ", item.get("abstract") or "")
            parts = item.get("issued", {}).get("date-parts", [[None]])
            year = parts[0][0] if parts and parts[0] else None
            retrieved = f"{year}-01-01T00:00:00+00:00" if year else None
            licenses = item.get("license") or [{}]
            units.append(
                self._unit(
                    title=title,
                    summary=abstract,
                    url=item.get("URL", ""),
                    concepts=tuple(item.get("container-title") or ()),
                    tags=("paper", "crossref"),
                    license=licenses[0].get("URL", ""),
                    retrieved_at=retrieved,
                )
            )
        return units[:limit]


class HuggingFaceGuardian(HttpGuardian):
    name = "huggingface"
    base_confidence = 0.5
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            f"https://huggingface.co/api/models?search={quote(query)}"
            f"&limit={limit}&sort=downloads&direction=-1"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for model in data if isinstance(data, list) else []:
            model_id = model.get("modelId") or model.get("id") or ""
            if not model_id:
                continue
            downloads = int(model.get("downloads") or 0)
            confidence = min(0.9, 0.45 + math.log10(downloads + 1) / 10)
            units.append(
                self._unit(
                    title=model_id,
                    summary=model.get("pipeline_tag") or "",
                    url=f"https://huggingface.co/{model_id}",
                    concepts=tuple(
                        tag for tag in (model.get("tags") or [])[:5] if isinstance(tag, str)
                    ),
                    tags=("model", "huggingface"),
                    confidence=confidence,
                )
            )
        return units[:limit]


class NpmGuardian(HttpGuardian):
    name = "npm"
    base_confidence = 0.5
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = f"https://registry.npmjs.org/-/v1/search?text={quote(query)}&size={limit}"
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for entry in data.get("objects", []):
            package = entry.get("package", {})
            name = package.get("name") or ""
            if not name:
                continue
            score = float(entry.get("score", {}).get("final", 0) or 0)
            links = package.get("links") or {}
            units.append(
                self._unit(
                    title=name,
                    summary=package.get("description") or "",
                    url=links.get("npm") or f"https://www.npmjs.com/package/{name}",
                    concepts=tuple(package.get("keywords") or ())[:6],
                    tags=("package", "npm"),
                    confidence=min(0.85, 0.4 + score * 0.5),
                )
            )
        return units[:limit]


_CORPUS: tuple[dict, ...] = (
    {
        "slug": "best-first-search",
        "title": "Best-first search",
        "summary": "A graph search that expands the most promising node first using a "
        "priority queue and an admissible heuristic; complete when the heuristic is "
        "finite and the state space is finite.",
        "concepts": ("planning", "search", "heuristic", "priority queue"),
        "tags": ("algorithm",),
    },
    {
        "slug": "planning-as-graph-search",
        "title": "Planning as graph search",
        "summary": "Classical planning finds a sequence of operators that transforms an "
        "initial state into a goal state; it can be solved by forward search over the "
        "state space with regression or progression.",
        "concepts": ("planning", "state space", "operator", "goal"),
        "tags": ("algorithm", "planning"),
    },
    {
        "slug": "sqlite-wal",
        "title": "SQLite write-ahead logging",
        "summary": "WAL mode lets readers proceed while a writer appends to a log, "
        "improving concurrency for a single-writer workload; it is enabled with "
        "PRAGMA journal_mode=WAL.",
        "concepts": ("sqlite", "concurrency", "storage", "wal"),
        "tags": ("database",),
    },
    {
        "slug": "hashing-trick",
        "title": "Feature hashing",
        "summary": "Mapping tokens into fixed-width vectors with a signed hash yields a "
        "deterministic, model-free embedding suitable for lexical retrieval.",
        "concepts": ("embedding", "hashing", "retrieval", "vector"),
        "tags": ("nlp",),
    },
    {
        "slug": "capability-registry",
        "title": "Capability registry",
        "summary": "A versioned registry of executable capabilities with an activation "
        "status supports hot-swap and rollback: new versions are admitted only after "
        "verification, and a bad version can be rolled back.",
        "concepts": ("capability", "registry", "versioning", "rollback"),
        "tags": ("architecture",),
    },
    {
        "slug": "subprocess-sandbox",
        "title": "Subprocess isolation",
        "summary": "Running generated code in a separate process with a timeout and no "
        "inherited secrets contains crashes and runaway loops, and gives a hard "
        "verification gate before admitting the code.",
        "concepts": ("sandbox", "subprocess", "verification", "isolation"),
        "tags": ("security",),
    },
    {
        "slug": "evidence-based-claims",
        "title": "Evidence-based claims",
        "summary": "A claim should be accepted only when it is backed by evidence that "
        "can be independently checked; unevidenced assertions are hypotheses and must "
        "not be reported as results.",
        "concepts": ("evidence", "validation", "provenance", "integrity"),
        "tags": ("method",),
    },
    {
        "slug": "failure-memo",
        "title": "Failure memoisation",
        "summary": "Recording the signature of an attempted branch and its failure "
        "reason lets a planner prune already-proven dead ends on later runs, so every "
        "error becomes a reusable constraint.",
        "concepts": ("search", "pruning", "memoisation", "learning"),
        "tags": ("algorithm",),
    },
    {
        "slug": "rate-limiting",
        "title": "Token-bucket rate limiting",
        "summary": "Spacing calls to an external API with a minimum interval respects "
        "the provider's usage policy and avoids throttling or bans.",
        "concepts": ("rate limit", "api", "politeness", "throttling"),
        "tags": ("network",),
    },
    {
        "slug": "provenance",
        "title": "Data provenance",
        "summary": "Recording source, URL, retrieval time and licence for every fact "
        "makes the knowledge base auditable and lets stale or untrusted items be "
        "identified.",
        "concepts": ("provenance", "audit", "licence", "trust"),
        "tags": ("method",),
    },
    {
        "slug": "openalex",
        "title": "OpenAlex scholarly index",
        "summary": "OpenAlex is an open catalogue of scholarly works with a JSON API; "
        "abstracts are returned as an inverted index that must be reconstructed into "
        "ordered text.",
        "concepts": ("openalex", "papers", "api", "abstract"),
        "tags": ("source",),
    },
    {
        "slug": "quantum-simulator-limits",
        "title": "Quantum simulator limits",
        "summary": "A classical simulator of a quantum circuit reproduces outcomes but "
        "gives no asymptotic speedup; it costs more than the classical algorithm it "
        "simulates. Real advantage requires quantum hardware.",
        "concepts": ("quantum", "simulation", "complexity", "limits"),
        "tags": ("honesty",),
    },
)


class WikipediaGuardian(HttpGuardian):
    name = "wikipedia"
    base_confidence = 0.6
    min_interval = 0.1

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={quote(query)}&srlimit={limit}&format=json&utf8=1"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title") or ""
            if not title.strip():
                continue
            pageid = item.get("pageid")
            link = (
                f"https://en.wikipedia.org/?curid={pageid}"
                if pageid
                else "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
            )
            units.append(
                self._unit(
                    title=title,
                    summary=_plain(item.get("snippet") or ""),
                    url=link,
                    tags=("encyclopedia", "wikipedia"),
                    license="CC BY-SA 4.0",
                )
            )
        return units[:limit]


class StackExchangeGuardian(HttpGuardian):
    name = "stackexchange"
    base_confidence = 0.55
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = (
            "https://api.stackexchange.com/2.3/search/advanced"
            f"?order=desc&sort=relevance&q={quote(query)}&site=stackoverflow"
            f"&pagesize={limit}&filter=withbody"
        )
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for item in data.get("items", []):
            title = item.get("title") or ""
            if not title.strip():
                continue
            score = int(item.get("score") or 0)
            units.append(
                self._unit(
                    title=title,
                    summary=_plain(item.get("body") or "")[:600],
                    url=item.get("link") or "",
                    concepts=tuple(item.get("tags") or ()),
                    tags=("qa", "stackoverflow"),
                    confidence=min(0.8, 0.5 + 0.03 * max(0, score)),
                    license="CC BY-SA 4.0",
                )
            )
        return units[:limit]


class ZenodoGuardian(HttpGuardian):
    name = "zenodo"
    base_confidence = 0.6
    min_interval = 0.2

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        url = f"https://zenodo.org/api/records?q={quote(query)}&size={limit}&sort=mostrecent"
        data = json.loads(self._get(url))
        units: list[KnowledgeUnit] = []
        for hit in data.get("hits", {}).get("hits", []):
            meta = hit.get("metadata", {})
            title = meta.get("title") or ""
            if not title.strip():
                continue
            links = hit.get("links", {}) or {}
            resource = (meta.get("resource_type") or {}).get("title") or "record"
            license_info = meta.get("license") or {}
            units.append(
                self._unit(
                    title=title,
                    summary=_plain(meta.get("description") or "")[:800],
                    url=links.get("self_html") or links.get("html") or "",
                    concepts=(resource,),
                    tags=("dataset", "zenodo"),
                    license=license_info.get("id") or "Zenodo",
                    retrieved_at=meta.get("publication_date"),
                )
            )
        return units[:limit]


class LocalGuardian:
    """Offline corpus of durable engineering knowledge. Always available."""

    name = "local"

    def __init__(self) -> None:
        self._units: list[KnowledgeUnit] = []
        for item in _CORPUS:
            text = " ".join(
                (item["title"], item["summary"], *item["concepts"], *item["tags"])
            )
            self._units.append(
                KnowledgeUnit(
                    id=f"local:{item['slug']}",
                    title=item["title"],
                    summary=item["summary"],
                    provenance=Provenance(
                        source="local",
                        url=f"local://{item['slug']}",
                        retrieved_at=utcnow(),
                        license="internal",
                        confidence=0.5,
                    ),
                    concepts=tuple(item["concepts"]),
                    tags=tuple(item["tags"]),
                    embedding=embed(text),
                )
            )

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        qvec = embed(query)
        scored = [(u, cosine(qvec, u.embedding)) for u in self._units]
        scored.sort(key=lambda pair: (-pair[1], pair[0].id))
        # A small floor rejects accidental hash collisions between unrelated texts.
        return [u for u, score in scored if score > 0.12][:limit]
