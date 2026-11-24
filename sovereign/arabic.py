"""Arabic-aware text normalization and tokenization.

The normalization is for retrieval, not for display: it removes diacritics and
tatweel, unifies alef/ya/ta-marbuta variants, and keeps Arabic letters and
digits. English text is left to whitespace splitting, so existing behaviour is
unchanged.
"""

from __future__ import annotations

import re

_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_TOKEN = re.compile(r"\w+")


def normalize_arabic(text: str) -> str:
    text = _DIACRITICS.sub("", text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
        .replace("ة", "ه")
    )
    return text


def tokenize_text(text: str) -> list[str]:
    if not _ARABIC.search(text):
        return text.split()
    return _TOKEN.findall(normalize_arabic(text))


def split_sentences(text: str) -> list[str]:
    normalized = text.replace("!", ".").replace("?", ".").replace("؟", ".").replace("۔", ".")
    return [sentence.strip() for sentence in normalized.split(".") if sentence.strip()]

_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
_SUFFIXES = ("ها", "ان", "ات", "ون", "ين", "ة", "ه", "ي")


def light_stem(word: str) -> str:
    """Strip common Arabic prefixes and suffixes; this is not morphology."""
    word = normalize_arabic(word)
    for prefix in _PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            word = word[len(prefix) :]
            break
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    return word


def stem_text(text: str) -> list[str]:
    return [light_stem(token) for token in tokenize_text(text)]

