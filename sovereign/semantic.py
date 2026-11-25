"""A distributional semantic index built from the knowledge corpus.

This is not a neural model. It learns positive pointwise mutual information
(PPMI) between words in a local window, projects each context through a
deterministic sparse random vector, and represents documents as the mean of
their word vectors. It gives the fabric a second, corpus-derived semantic
signal without downloading a model or adding a dependency.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict

from .vectors import tokenize


class SemanticIndex:
    def __init__(
        self,
        documents: dict[str, str],
        *,
        dim: int = 256,
        window: int = 2,
        nonzero: int = 8,
    ) -> None:
        self.dim = max(8, int(dim))
        self.window = max(1, int(window))
        self.nonzero = max(1, min(int(nonzero), self.dim))
        self.ids = list(documents)
        tokenized = [tokenize(documents[item]) for item in self.ids]
        vocabulary = Counter(token for tokens in tokenized for token in tokens)

        pair_counts: Counter[tuple[str, str]] = Counter()
        for tokens in tokenized:
            for index, token in enumerate(tokens):
                start = max(0, index - self.window)
                end = min(len(tokens), index + self.window + 1)
                for other_index in range(start, end):
                    if other_index != index:
                        pair_counts[(token, tokens[other_index])] += 1

        total = sum(pair_counts.values()) or 1
        row = Counter()
        column = Counter()
        contexts: dict[str, Counter[str]] = defaultdict(Counter)
        for (word, context), count in pair_counts.items():
            row[word] += count
            column[context] += count
            contexts[word][context] += count

        self.word_vectors: dict[str, list[float]] = {}
        for word in vocabulary:
            vector = [0.0] * self.dim
            for context, count in contexts.get(word, {}).items():
                pmi = math.log(
                    (count / total)
                    / ((row[word] / total) * (column[context] / total))
                )
                if pmi <= 0:
                    continue
                for index, sign in self._random_vector(context):
                    vector[index] += pmi * sign
            self.word_vectors[word] = _normalize(vector)

        self.document_vectors: dict[str, list[float]] = {}
        for item, tokens in zip(self.ids, tokenized):
            vectors = [self.word_vectors[token] for token in tokens if token in self.word_vectors]
            self.document_vectors[item] = _mean(vectors, self.dim)

    def _random_vector(self, token: str) -> list[tuple[int, float]]:
        result: list[tuple[int, float]] = []
        for position in range(self.nonzero):
            digest = hashlib.blake2b(
                f"{token}:{position}".encode("utf-8"), digest_size=8
            ).digest()
            value = int.from_bytes(digest, "big")
            result.append((value % self.dim, 1.0 if (value >> 63) & 1 else -1.0))
        return result

    def query_vector(self, query: str) -> list[float]:
        tokens = tokenize(query)
        vectors = [self.word_vectors[token] for token in tokens if token in self.word_vectors]
        return _mean(vectors, self.dim)

    def scores(self, query: str) -> dict[str, float]:
        query_vector = self.query_vector(query)
        if not any(query_vector):
            return {item: 0.0 for item in self.ids}
        return {
            item: sum(a * b for a, b in zip(query_vector, vector))
            for item, vector in self.document_vectors.items()
        }


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _mean(vectors: list[list[float]], dim: int) -> list[float]:
    if not vectors:
        return [0.0] * dim
    total = [0.0] * dim
    for vector in vectors:
        for index, value in enumerate(vector):
            total[index] += value
    return _normalize(total)
