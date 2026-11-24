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

_TOKEN = re.compile(r"[a-z0-9]+")
DEFAULT_DIM = 1024


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


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


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
