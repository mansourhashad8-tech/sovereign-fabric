"""Deterministic, dependency-free text embeddings.

A signed hashing bag-of-words. It is deliberately simple and reproducible:
the same text always yields the same vector, on any machine, with no model
download and no network. It is not a semantic embedding; it is a lexical
index that makes retrieval deterministic and offline-testable.
"""

from __future__ import annotations

import hashlib
import math
import re

from .arabic import normalize_arabic, stem_text

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
DEFAULT_DIM = 1024


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(normalize_arabic(text).lower())


def embed(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    vec = [0.0] * dim
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[h % dim] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm:
        vec = [v / norm for v in vec]
    return vec


def embed_query(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """Embed a query with a light Arabic stem variant mixed in.

    Documents keep their exact word vectors. Queries that can be stemmed are
    blended with the stemmed form, so ``الكتابات`` can reach ``كتاب`` without
    re-embedding the whole store.
    """
    base = embed(text, dim)
    stems = " ".join(stem_text(text))
    if not stems or stems == " ".join(tokenize(text)):
        return base
    alt = embed(stems, dim)
    mixed = [0.5 * a + 0.5 * b for a, b in zip(base, alt)]
    norm = math.sqrt(sum(v * v for v in mixed))
    return [v / norm for v in mixed] if norm else mixed


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
