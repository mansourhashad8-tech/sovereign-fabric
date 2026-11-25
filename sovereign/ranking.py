"""Lexical ranking and rank fusion for the fabric's retrieval layer.

The fabric's embeddings are deterministic feature hashes. They are cheap and
stable, but they blur exact rare terms. BM25 preserves those terms, and
reciprocal rank fusion combines the two rankings without pretending their
scores share a scale.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .arabic import normalize_arabic

_TOKEN = re.compile(r"[A-Za-z0-9\u0600-\u06FF]+")


def ranking_tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize_arabic(text).casefold())


class BM25Index:
    """Reusable BM25 statistics over an id-keyed document map."""

    def __init__(
        self, documents: dict[str, str], *, k1: float = 1.5, b: float = 0.75
    ) -> None:
        self.k1 = k1
        self.b = b
        self.ids = list(documents)
        self.tokenized = [ranking_tokens(documents[item]) for item in self.ids]
        self.frequencies = [Counter(tokens) for tokens in self.tokenized]
        self.lengths = [len(tokens) for tokens in self.tokenized]
        self.average_length = (
            sum(self.lengths) / len(self.lengths) if self.lengths else 1.0
        ) or 1.0
        self.document_frequency: Counter[str] = Counter()
        for tokens in self.tokenized:
            self.document_frequency.update(set(tokens))
        count = len(self.ids)
        self.idf = {
            term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in self.document_frequency.items()
        }

    def scores(self, query: str) -> dict[str, float]:
        query_terms = ranking_tokens(query)
        if not query_terms or not self.ids:
            return {item: 0.0 for item in self.ids}
        result: dict[str, float] = {}
        for item, frequencies, length in zip(
            self.ids, self.frequencies, self.lengths
        ):
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * (length / self.average_length)
                )
                score += self.idf.get(term, 0.0) * (
                    frequency * (self.k1 + 1.0)
                ) / denominator
            result[item] = score
        return result


def bm25_scores(
    query: str,
    documents: list[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Okapi BM25 over an explicit, bounded document list."""
    index = BM25Index(
        {str(position): document for position, document in enumerate(documents)},
        k1=k1,
        b=b,
    )
    scores = index.scores(query)
    return [scores[str(position)] for position in range(len(documents))]


def reciprocal_rank_fusion(
    rankings: list[list[str]], *, k: int = 60
) -> dict[str, float]:
    """Fuse ranked id lists; each list contributes 1/(k + rank)."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return fused


def ndcg_at_k(ranked: list[str], relevance: dict[str, float], *, k: int = 10) -> float:
    """Normalised discounted cumulative gain with binary or graded relevance."""
    k = max(1, min(int(k), 100))
    gains = {str(key): max(0.0, float(value)) for key, value in relevance.items()}
    dcg = 0.0
    for rank, item in enumerate(ranked[:k], 1):
        gain = gains.get(str(item), 0.0)
        if gain:
            dcg += (2**gain - 1) / math.log2(rank + 1)
    ideal = sorted(gains.values(), reverse=True)[:k]
    idcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, 1))
    return dcg / idcg if idcg else 0.0


def mrr(ranked: list[str], relevant: set[str]) -> float:
    """Reciprocal rank of the first relevant item; zero if none is present."""
    wanted = {str(item) for item in relevant}
    for rank, item in enumerate(ranked, 1):
        if str(item) in wanted:
            return 1.0 / rank
    return 0.0


def evaluate_ranking(
    ranked: list[str], relevance: dict[str, float], *, k: int = 10
) -> dict[str, float]:
    relevant = {key for key, value in relevance.items() if float(value) > 0}
    return {
        "ndcg": round(ndcg_at_k(ranked, relevance, k=k), 12),
        "mrr": round(mrr(ranked, relevant), 12),
        "k": max(1, min(int(k), 100)),
    }
