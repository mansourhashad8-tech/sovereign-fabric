"""A small trainable intent classifier for Arabic and English requests.

The keyword router remains the deterministic first pass. This model is a
multinomial Naive Bayes classifier over word and character n-gram features,
trained from a labelled seed set. It can be updated at runtime with
``IntentModel.learn`` and reports calibrated-by-softmax confidence. It is not a
language model, and its accuracy is measured on held-out examples.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Iterable

from .arabic import tokenize_text

_TRAINING: dict[str, tuple[str, ...]] = {
    "keywords": (
        "استخرج الكلمات المفتاحية",
        "key phrases from this text",
        "اعطني الكلمات المفتاحية",
    ),
    "stats": (
        "إحصاءات النص",
        "text statistics",
        "readability statistics",
    ),
    "language": (
        "ما لغة هذا النص",
        "detect the language",
        "language identification",
    ),
    "sentences": (
        "قسّم النص إلى جمل",
        "split this into sentences",
        "count the sentences",
    ),
    "redact": (
        "احجب البيانات الحساسة",
        "redact emails and secrets",
        "remove sensitive information",
    ),
    "entities": (
        "استخرج الكيانات",
        "named entities in this text",
        "recognize entities",
    ),
    "hash": (
        "احسب هاش النص",
        "sha256 hash this string",
        "hash the text",
    ),
    "base64": (
        "رمز النص base64",
        "encode this as base64",
        "base64 decode",
    ),
    "similarity": (
        "قارن تشابه النصين",
        "text similarity",
        "how similar are these texts",
    ),
    "math": (
        "احسب 2 + 2",
        "calculate 12 * 3",
        "solve this math expression",
    ),
    "date": (
        "أضف 3 أيام إلى التاريخ",
        "date difference",
        "business days between dates",
    ),
    "url": (
        "حلل الرابط",
        "parse this url",
        "url query parameters",
    ),
    "json": (
        "نسّق json",
        "pretty print json",
        "validate this json",
    ),
    "csv": (
        "حوّل csv إلى json",
        "parse csv columns",
        "csv to table",
    ),
    "toml": (
        "parse toml",
        "toml to json",
        "read toml configuration",
    ),
    "ini": (
        "parse ini file",
        "ini sections",
        "read ini configuration",
    ),
    "html": (
        "استخرج نص html",
        "html to text",
        "links in html",
    ),
    "headings": (
        "استخرج العناوين",
        "markdown headings",
        "list headings",
    ),
    "summary": (
        "لخص النص",
        "summarize this text",
        "give me a summary",
    ),
    "counts": (
        "عدد الكلمات",
        "count words",
        "word frequency",
    ),
    "tokens": (
        "قسّم النص إلى كلمات",
        "tokenize this text",
        "tokens in the text",
    ),
    "markdown": (
        "اكتب تقريرا",
        "write a report",
        "markdown brief",
    ),
}

_LABELS = tuple(_TRAINING)
_MAX_UPDATES = 5000


def _features(text: str) -> list[str]:
    features: list[str] = []
    for token in tokenize_text(text.lower()):
        features.append("w:" + token)
        if len(token) >= 3:
            for index in range(len(token) - 2):
                features.append("c:" + token[index : index + 3])
    return features


class IntentModel:
    def __init__(self, training: dict[str, Iterable[str]] | None = None) -> None:
        self.counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.totals: Counter[str] = Counter()
        self.documents: Counter[str] = Counter()
        self.vocabulary: set[str] = set()
        self.updates = 0
        source = _TRAINING if training is None else training
        for label, examples in source.items():
            for example in examples:
                self.learn(example, label)

    def learn(self, text: str, label: str) -> bool:
        text = text.strip()[:500]
        label = label.strip()[:64]
        if not text or not label or self.updates >= _MAX_UPDATES:
            return False
        features = _features(text)
        if not features:
            return False
        self.counts[label].update(features)
        self.totals[label] += len(features)
        self.documents[label] += 1
        self.vocabulary.update(features)
        self.updates += 1
        return True

    def classify(self, text: str) -> dict[str, object]:
        features = _features(text)
        if not features or not self.documents:
            return {"label": None, "confidence": 0.0, "top": []}
        total_documents = sum(self.documents.values())
        vocabulary_size = max(1, len(self.vocabulary))
        scores: dict[str, float] = {}
        for label, documents in self.documents.items():
            score = math.log((documents + 1) / (total_documents + len(self.documents)))
            denominator = self.totals[label] + vocabulary_size
            for feature in features:
                score += math.log((self.counts[label][feature] + 1) / denominator)
            scores[label] = score
        best_score = max(scores.values())
        normalizer = best_score + math.log(
            sum(math.exp(score - best_score) for score in scores.values())
        )
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return {
            "label": ranked[0][0],
            "confidence": math.exp(ranked[0][1] - normalizer),
            "top": [
                {"label": label, "confidence": math.exp(score - normalizer)}
                for label, score in ranked[:3]
            ],
        }

    def evaluate(self, examples: Iterable[tuple[str, str]]) -> dict[str, object]:
        rows = list(examples)
        correct = 0
        failures: list[dict[str, str]] = []
        for text, expected in rows:
            predicted = str(self.classify(text)["label"])
            if predicted == expected:
                correct += 1
            else:
                failures.append({"text": text, "expected": expected, "predicted": predicted})
        return {
            "examples": len(rows),
            "correct": correct,
            "accuracy": round(correct / len(rows), 4) if rows else 0.0,
            "failures": failures,
        }

    def status(self) -> dict[str, object]:
        return {
            "labels": sorted(self.documents),
            "documents": sum(self.documents.values()),
            "features": len(self.vocabulary),
            "updates": self.updates,
            "max_updates": _MAX_UPDATES,
        }


_MODEL = IntentModel()


def default_model() -> IntentModel:
    return _MODEL
