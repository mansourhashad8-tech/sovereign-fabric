"""Extra built-in capabilities: data, text, math, dates, URLs, and privacy.

Every function takes a payload dict and returns ``{"value": ...}``. The
capabilities are pure, bounded, and do not perform network I/O. They are
registered separately from the five-capability native chain so the original
planner path stays stable.
"""

from __future__ import annotations

import ast
import base64
import configparser
import csv
import difflib
import hashlib
from html.parser import HTMLParser
import io
import json
import math
import operator
import re
import statistics
import string
import tomllib
import unicodedata
import urllib.parse
import uuid
from datetime import date, timedelta
from itertools import islice
from typing import Any

from .arabic import normalize_arabic, split_sentences, tokenize_text
from .capabilities import CapabilityRegistry
from .models import Capability, Provenance

_EN_STOP = frozenset(
    "a an the and or but if then else for of to in on at by with from as is are "
    "was were be been being it this that these those i you he she we they".split()
)
_AR_STOP = frozenset(
    "في من على الي إلى عن مع هذا هذه ذلك تلك هو هي هم انا أنا انت أنت نحن كان "
    "كانت يكون تكون لا ما هل ثم او أو و".split()
)
_STOP = _EN_STOP | _AR_STOP

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"https?://[^\s<>\"']+")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_HASHTAG = re.compile(r"#[\w\u0600-\u06ff]+")
_MENTION = re.compile(r"(?<![\w.])@[\w.]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_LONG_HEX = re.compile(r"\b[A-Fa-f0-9]{32,}\b")


def _text(payload: dict[str, Any]) -> str:
    return str(payload.get("value", ""))


def _words(text: str) -> list[str]:
    if re.search(r"[\u0600-\u06ff]", text):
        text = normalize_arabic(text)
    return re.findall(r"\w+", text)


def _bounded(payload: dict[str, Any], name: str, default: int, cap: int) -> int:
    try:
        value = int(payload.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, cap))


def text_clean(payload: dict[str, Any]) -> dict[str, Any]:
    text = unicodedata.normalize("NFKC", _text(payload))
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return {"value": text}


def text_sentences(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": split_sentences(_text(payload))}


def sentences_stats(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("value") or []
    sentences = value if isinstance(value, list) else split_sentences(str(value))
    sentences = [str(item).strip() for item in sentences if str(item).strip()]
    words = sum(len(tokenize_text(item)) for item in sentences)
    return {
        "value": {
            "sentences": len(sentences),
            "words": words,
            "avg_words": round(words / len(sentences), 2) if sentences else 0.0,
        }
    }


def text_stats(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    tokens = _words(text)
    sentences = split_sentences(text)
    return {
        "value": {
            "chars": len(text),
            "words": len(tokens),
            "unique_words": len({token.lower() for token in tokens}),
            "sentences": len(sentences),
            "avg_word_len": round(sum(map(len, tokens)) / len(tokens), 2) if tokens else 0.0,
        }
    }


def text_langdetect(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    counts = {
        "arabic": len(re.findall(r"[\u0600-\u06ff]", text)),
        "latin": len(re.findall(r"[A-Za-z\u00c0-\u024f]", text)),
        "cyrillic": len(re.findall(r"[\u0400-\u04ff]", text)),
        "cjk": len(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text)),
        "digits": len(re.findall(r"\d", text)),
    }
    dominant = max(counts, key=counts.get) if any(counts.values()) else "unknown"
    return {"value": {"script": dominant, "counts": counts}}


def text_keywords(payload: dict[str, Any]) -> dict[str, Any]:
    limit = _bounded(payload, "limit", 10, 50)
    counts: dict[str, int] = {}
    for token in [item.lower() for item in _words(_text(payload))]:
        if token in _STOP or len(token) < 2:
            continue
        counts[token] = counts.get(token, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return {"value": [{"term": term, "count": count} for term, count in top]}


def text_ngrams(payload: dict[str, Any]) -> dict[str, Any]:
    n = _bounded(payload, "n", 2, 4)
    tokens = _words(_text(payload))
    counts: dict[str, int] = {}
    for index in range(len(tokens) - n + 1):
        gram = " ".join(tokens[index : index + n])
        counts[gram] = counts.get(gram, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:50]
    return {"value": [{"gram": gram, "count": count} for gram, count in top]}


def text_entities(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    return {
        "value": {
            "emails": _EMAIL.findall(text)[:50],
            "urls": _URL.findall(text)[:50],
            "dates": _DATE.findall(text)[:50],
            "numbers": _NUMBER.findall(text)[:50],
            "hashtags": _HASHTAG.findall(text)[:50],
            "mentions": _MENTION.findall(text)[:50],
        }
    }


def text_redact(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    replacements = 0

    def replace(pattern: re.Pattern[str], label: str, source: str) -> str:
        nonlocal replacements

        def _sub(_: re.Match[str]) -> str:
            nonlocal replacements
            replacements += 1
            return label

        return pattern.sub(_sub, source)

    text = replace(_EMAIL, "[EMAIL]", text)
    text = replace(_IPV4, "[IP]", text)
    text = replace(_PHONE, "[PHONE]", text)
    text = replace(_LONG_HEX, "[SECRET]", text)
    return {"value": text, "replacements": replacements}


def tokens_top(payload: dict[str, Any]) -> dict[str, Any]:
    limit = _bounded(payload, "limit", 10, 50)
    tokens = payload.get("value") or []
    counts: dict[str, int] = {}
    for token in tokens:
        term = str(token).lower()
        if term in _STOP or len(term) < 2:
            continue
        counts[term] = counts.get(term, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return {"value": [[term, count] for term, count in top]}


def _pair(payload: dict[str, Any]) -> tuple[str, str]:
    value = payload.get("value")
    if isinstance(value, dict):
        return str(value.get("a", "")), str(value.get("b", ""))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return str(value[0]), str(value[1])
    text = str(value or "")
    for separator in ("|||", "\n---\n", "\n"):
        if separator in text:
            left, right = text.split(separator, 1)
            return left, right
    return text, ""


def text_similarity(payload: dict[str, Any]) -> dict[str, Any]:
    left, right = _pair(payload)
    a = {item.lower() for item in tokenize_text(left) if item.lower() not in _STOP}
    b = {item.lower() for item in tokenize_text(right) if item.lower() not in _STOP}
    union = a | b
    intersection = a & b
    return {
        "value": {
            "jaccard": round(len(intersection) / len(union), 4) if union else 0.0,
            "shared": sorted(intersection)[:50],
            "left_terms": len(a),
            "right_terms": len(b),
        }
    }


def json_validate(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(_text(payload))
    except Exception as exc:
        return {"value": {"valid": False, "error": f"{type(exc).__name__}: {exc}"}}
    return {"value": {"valid": True, "type": type(value).__name__}}


def json_pretty(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 100_000:
        raise ValueError("JSON input exceeds 100000 characters")
    value = json.loads(text)
    return {"value": json.dumps(value, indent=2, ensure_ascii=False)}


def csv_parse(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("CSV input exceeds 200000 characters")
    has_header = bool(payload.get("has_header", True))
    reader = csv.reader(io.StringIO(text))
    rows = list(islice(reader, 1001))
    if len(rows) > 1000:
        raise ValueError("CSV exceeds 1000 rows")
    if not rows:
        return {"value": {"columns": [], "rows": []}}
    width = max(len(row) for row in rows)
    if width > 50:
        raise ValueError("CSV exceeds 50 columns")
    if has_header:
        columns = rows[0]
        body = rows[1:]
    else:
        columns = [f"c{index}" for index in range(width)]
        body = rows
    return {"value": {"columns": columns, "rows": [list(row) for row in body]}}


def _table(payload: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    value = payload.get("value")
    if not isinstance(value, dict):
        raise ValueError("table must be an object with columns and rows")
    columns = list(value.get("columns") or [])
    rows = [list(row) for row in (value.get("rows") or [])]
    if not columns or not rows:
        return columns, rows
    if len(rows) > 5000:
        raise ValueError("table exceeds 5000 rows")
    width = len(columns)
    rows = [(row + [""] * width)[:width] for row in rows]
    return columns, rows


def table_sort(payload: dict[str, Any]) -> dict[str, Any]:
    columns, rows = _table(payload)
    if not columns or not rows:
        return {"value": {"columns": columns, "rows": rows}}
    column = payload.get("column", 0)
    index = columns.index(column) if isinstance(column, str) and column in columns else int(column)
    reverse = bool(payload.get("desc", False))
    rows.sort(key=lambda row: (row[index] is None, str(row[index])), reverse=reverse)
    return {"value": {"columns": columns, "rows": rows}}


def table_filter(payload: dict[str, Any]) -> dict[str, Any]:
    columns, rows = _table(payload)
    if not columns:
        return {"value": {"columns": columns, "rows": rows}}
    column = payload.get("column", 0)
    index = columns.index(column) if isinstance(column, str) and column in columns else int(column)
    expected = str(payload.get("equals", ""))
    kept = [row for row in rows if str(row[index]) == expected]
    return {"value": {"columns": columns, "rows": kept, "matched": len(kept)}}


def markdown_table(payload: dict[str, Any]) -> dict[str, Any]:
    columns, rows = _table(payload)
    if not columns:
        return {"value": "(empty table)"}
    escape = lambda value: str(value).replace("|", "\\|")
    lines = ["| " + " | ".join(escape(item) for item in columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows[:200]:
        lines.append("| " + " | ".join(escape(item) for item in row) + " |")
    return {"value": "\n".join(lines)}


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _eval_math(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval_math(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        if isinstance(node.op, ast.Pow):
            exponent = _eval_math(node.right)
            if abs(exponent) > 1000:
                raise ValueError("exponent exceeds 1000")
            return _BINOPS[type(node.op)](_eval_math(node.left), exponent)
        return _BINOPS[type(node.op)](_eval_math(node.left), _eval_math(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_math(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise ValueError(f"unsupported expression node: {type(node).__name__}")


def math_eval(payload: dict[str, Any]) -> dict[str, Any]:
    expression = _text(payload).strip()
    if not expression or len(expression) > 200:
        raise ValueError("expression must be 1..200 characters")
    result = _eval_math(ast.parse(expression, mode="eval"))
    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("result is not finite")
    if isinstance(result, int) and result.bit_length() > 10_000:
        raise ValueError("integer result is too large")
    return {"value": result}


def date_diff(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    parts = [item for item in re.split(r"[,\s]+", text) if item]
    if len(parts) != 2:
        raise ValueError("provide exactly two ISO dates (YYYY-MM-DD)")
    first, second = (date.fromisoformat(item) for item in parts)
    return {"value": {"from": first.isoformat(), "to": second.isoformat(), "days": (second - first).days}}


def url_parse(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    parsed = urllib.parse.urlsplit(text)
    if not parsed.scheme:
        raise ValueError("URL has no scheme")
    return {
        "value": {
            "scheme": parsed.scheme,
            "netloc": parsed.netloc,
            "path": parsed.path,
            "query": parsed.query,
            "fragment": parsed.fragment,
        }
    }


def base64_encode(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 100_000:
        raise ValueError("input exceeds 100000 characters")
    return {"value": base64.b64encode(text.encode("utf-8")).decode("ascii")}


def base64_decode(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip()
    if len(text) > 200_000:
        raise ValueError("input exceeds 200000 characters")
    raw = base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
    return {"value": raw.decode("utf-8", "replace")}


def hash_sha256(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": hashlib.sha256(_text(payload).encode("utf-8")).hexdigest()}


def uuid_generate(payload: dict[str, Any]) -> dict[str, Any]:
    count = _bounded(payload, "count", 1, 20)
    return {"value": [str(uuid.uuid4()) for _ in range(count)]}


def template_render(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("value")
    if not isinstance(value, dict):
        raise ValueError("template payload must be {template, values}")
    template = str(value.get("template", ""))
    values = value.get("values") or {}
    if not isinstance(values, dict):
        raise ValueError("values must be an object")
    return {"value": string.Template(template).safe_substitute({str(k): str(v) for k, v in values.items()})}


def text_arabic_normalize(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": normalize_arabic(_text(payload))}


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def text_arabic_digits(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": _text(payload).translate(_ARABIC_DIGITS)}


def text_arabic_stem(payload: dict[str, Any]) -> dict[str, Any]:
    stems: list[str] = []
    for token in _words(_text(payload)):
        word = token
        for prefix in ("وال", "بال", "كال", "فال", "لل", "ال"):
            if word.startswith(prefix) and len(word) - len(prefix) >= 3:
                word = word[len(prefix) :]
                break
        for suffix in ("ها", "ان", "ات", "ون", "ين", "ة", "ه", "ي"):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                word = word[: -len(suffix)]
                break
        stems.append(word)
    return {"value": stems}


def text_stopwords(payload: dict[str, Any]) -> dict[str, Any]:
    kept = [word for word in _words(_text(payload)) if word.lower() not in _STOP]
    return {"value": " ".join(kept)}


def text_unique_lines(payload: dict[str, Any]) -> dict[str, Any]:
    seen: set[str] = set()
    lines: list[str] = []
    for line in _text(payload).splitlines():
        item = line.strip()
        if item and item not in seen:
            seen.add(item)
            lines.append(item)
    return {"value": "\n".join(lines)}


def text_excerpt(payload: dict[str, Any]) -> dict[str, Any]:
    limit = _bounded(payload, "limit", 200, 2000)
    text = _text(payload)
    return {"value": text[:limit] + ("…" if len(text) > limit else "")}


def json_get(payload: dict[str, Any]) -> dict[str, Any]:
    path = str(payload.get("path", "")).strip()
    if not path or len(path) > 200:
        raise ValueError("path must be 1..200 characters")
    value = json.loads(_text(payload))
    for part in path.split("."):
        if isinstance(value, list):
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise KeyError(part)
    return {"value": value}


def json_minify(payload: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(_text(payload))
    return {"value": json.dumps(value, separators=(",", ":"), ensure_ascii=False)}


def csv_to_json(payload: dict[str, Any]) -> dict[str, Any]:
    table = csv_parse(payload)["value"]
    columns = table["columns"]
    records = [dict(zip(columns, row)) for row in table["rows"]]
    return {"value": json.dumps(records, ensure_ascii=False)}


def table_aggregate(payload: dict[str, Any]) -> dict[str, Any]:
    columns, rows = _table(payload)
    if not columns:
        raise ValueError("table has no columns")
    column = payload.get("column", 0)
    index = columns.index(column) if isinstance(column, str) and column in columns else int(column)
    op = str(payload.get("op", "sum")).lower()
    if op not in {"sum", "avg", "min", "max", "count"}:
        raise ValueError("op must be sum, avg, min, max, or count")
    raw = [row[index] for row in rows]
    if op == "count":
        return {"value": {"column": columns[index], "op": op, "result": len(raw)}}
    numbers: list[float] = []
    for item in raw:
        try:
            numbers.append(float(item))
        except (TypeError, ValueError):
            raise ValueError(f"non-numeric value in column {columns[index]!r}")
    if not numbers:
        raise ValueError("no numeric values")
    if op == "sum":
        result = sum(numbers)
    elif op == "avg":
        result = sum(numbers) / len(numbers)
    elif op == "min":
        result = min(numbers)
    else:
        result = max(numbers)
    return {"value": {"column": columns[index], "op": op, "result": result}}


def _numbers(payload: dict[str, Any]) -> list[float]:
    value = payload.get("value")
    items = value if isinstance(value, list) else re.split(r"[,\s]+", str(value or ""))
    items = [item for item in items if str(item).strip()]
    if not items:
        raise ValueError("no numbers supplied")
    if len(items) > 10_000:
        raise ValueError("too many numbers")
    try:
        return [float(item) for item in items]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric input: {exc}") from exc


def math_stats(payload: dict[str, Any]) -> dict[str, Any]:
    numbers = _numbers(payload)
    return {
        "value": {
            "count": len(numbers),
            "sum": sum(numbers),
            "mean": statistics.fmean(numbers),
            "median": statistics.median(numbers),
            "stdev": statistics.pstdev(numbers),
            "min": min(numbers),
            "max": max(numbers),
        }
    }


def date_add(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip()
    days = int(payload.get("days", 0))
    if abs(days) > 36500:
        raise ValueError("days must be within +/-36500")
    return {"value": (date.fromisoformat(text) + timedelta(days=days)).isoformat()}


def date_weekday(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip()
    parsed = date.fromisoformat(text)
    return {"value": {"date": text, "weekday": parsed.strftime("%A"), "iso": parsed.isoweekday()}}


def url_query(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(_text(payload))
    return {"value": {key: values for key, values in urllib.parse.parse_qs(parsed.query, keep_blank_values=True).items()}}


def text_diff(payload: dict[str, Any]) -> dict[str, Any]:
    left, right = _pair(payload)
    a = left.splitlines()[:200]
    b = right.splitlines()[:200]
    diff = list(difflib.unified_diff(a, b, fromfile="left", tofile="right", lineterm=""))
    return {"value": "\n".join(diff[:400])}


def uuid_validate(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip()
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError):
        return {"value": {"valid": False, "version": None}}
    return {"value": {"valid": True, "version": parsed.version, "canonical": str(parsed)}}


def regex_escape(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": re.escape(_text(payload))}


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        if tag == "a":
            for key, value in attrs:
                if key == "href" and value:
                    self.links.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _html(payload: dict[str, Any]) -> _HTMLText:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("HTML input exceeds 200000 characters")
    parser = _HTMLText()
    parser.feed(text)
    return parser


def html_text(payload: dict[str, Any]) -> dict[str, Any]:
    parser = _html(payload)
    text = " ".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return {"value": text[:200_000]}


def html_links(payload: dict[str, Any]) -> dict[str, Any]:
    parser = _html(payload)
    return {"value": parser.links[:100]}


def toml_parse(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("TOML input exceeds 200000 characters")
    return {"value": json.dumps(tomllib.loads(text), ensure_ascii=False)}


def ini_parse(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("INI input exceeds 200000 characters")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    data = {section: dict(parser.items(section)) for section in parser.sections()}
    return {"value": json.dumps(data, ensure_ascii=False)}


def markdown_headings(payload: dict[str, Any]) -> dict[str, Any]:
    headings: list[dict[str, Any]] = []
    for line in _text(payload).splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            headings.append({"level": len(match.group(1)), "text": match.group(2)})
        if len(headings) >= 200:
            break
    return {"value": headings}


EXTRAS: dict[str, tuple[Any, str, tuple[str, ...], tuple[str, ...]]] = {
    "text.clean": (text_clean, "Normalize unicode and collapse whitespace", ("dirty_text",), ("text",)),
    "text.sentences": (text_sentences, "Split text into sentences (Arabic-aware)", ("text",), ("sentences",)),
    "sentences.stats": (sentences_stats, "Sentence and word counts", ("sentences",), ("sentence_stats",)),
    "text.stats": (text_stats, "Character, word, sentence, and uniqueness counts", ("text",), ("text_stats",)),
    "text.langdetect": (text_langdetect, "Detect the dominant script, not the language", ("text",), ("language",)),
    "text.keywords": (text_keywords, "Frequency keywords with stopword filtering", ("text",), ("keywords",)),
    "text.ngrams": (text_ngrams, "Top n-grams", ("text",), ("ngrams",)),
    "text.entities": (text_entities, "Regex entities: emails, URLs, dates, numbers, hashtags", ("text",), ("entities",)),
    "text.redact": (text_redact, "Redact emails, phones, IPs, and long hex secrets", ("text",), ("redacted_text",)),
    "tokens.top": (tokens_top, "Top non-stopword tokens", ("tokens",), ("top_tokens",)),
    "text.similarity": (text_similarity, "Jaccard similarity between two texts", ("text_pair",), ("similarity",)),
    "json.validate": (json_validate, "Validate JSON and report its type", ("json_text",), ("json_status",)),
    "json.pretty": (json_pretty, "Pretty-print JSON", ("json_text",), ("json_pretty",)),
    "csv.parse": (csv_parse, "Parse CSV into columns and rows (bounded)", ("csv_text",), ("table",)),
    "table.sort": (table_sort, "Sort a table by column", ("table",), ("table",)),
    "table.filter": (table_filter, "Filter a table by exact column value", ("table",), ("table",)),
    "markdown.table": (markdown_table, "Render a table as Markdown", ("table",), ("markdown",)),
    "math.eval": (math_eval, "Evaluate arithmetic with a whitelisted AST", ("expression",), ("number",)),
    "date.diff": (date_diff, "Days between two ISO dates", ("dates",), ("days",)),
    "url.parse": (url_parse, "Split a URL into components without fetching it", ("url",), ("url_parts",)),
    "base64.encode": (base64_encode, "Base64-encode UTF-8 text", ("text",), ("base64",)),
    "base64.decode": (base64_decode, "Decode base64 into text", ("base64",), ("text",)),
    "hash.sha256": (hash_sha256, "SHA-256 digest of text", ("text",), ("digest",)),
    "uuid.generate": (uuid_generate, "Generate random UUIDs", ("uuid_request",), ("uuids",)),
    "template.render": (template_render, "Render $placeholders without expression evaluation", ("template",), ("rendered_text",)),
    "text.arabic_normalize": (text_arabic_normalize, "Normalize Arabic letters, diacritics, and tatweel", ("text",), ("text",)),
    "text.arabic_digits": (text_arabic_digits, "Convert Arabic-Indic digits to ASCII digits", ("text",), ("text",)),
    "text.arabic_stem": (text_arabic_stem, "Light rule-based Arabic stemmer (not morphology)", ("text",), ("stems",)),
    "text.stopwords": (text_stopwords, "Remove Arabic and English stopwords", ("text",), ("text",)),
    "text.unique_lines": (text_unique_lines, "Deduplicate non-empty lines, order preserved", ("text",), ("text",)),
    "text.excerpt": (text_excerpt, "Bounded text excerpt with an ellipsis", ("text",), ("text_excerpt",)),
    "json.get": (json_get, "Read a dotted path from a JSON document", ("json_text",), ("json_value",)),
    "json.minify": (json_minify, "Minify JSON without changing its value", ("json_text",), ("json_minified",)),
    "csv.to_json": (csv_to_json, "Convert a bounded CSV table to JSON records", ("csv_text",), ("json_text",)),
    "table.aggregate": (table_aggregate, "Sum, average, min, max, or count a table column", ("table",), ("aggregate",)),
    "math.stats": (math_stats, "Count, sum, mean, median, stdev, min, max", ("math_values",), ("math_stats",)),
    "date.add": (date_add, "Add days to an ISO date", ("date",), ("date",)),
    "date.weekday": (date_weekday, "Weekday name and ISO number for a date", ("date",), ("weekday",)),
    "url.query": (url_query, "Parse URL query parameters", ("url",), ("url_query",)),
    "text.diff": (text_diff, "Unified diff of two bounded texts", ("text_pair",), ("diff",)),
    "uuid.validate": (uuid_validate, "Validate a UUID and report its version", ("uuid",), ("uuid_status",)),
    "regex.escape": (regex_escape, "Escape text for literal use in a regex", ("text",), ("regex_escaped",)),
    "html.text": (html_text, "Strip HTML tags, scripts, and styles into text", ("html_text",), ("text",)),
    "html.links": (html_links, "Extract href links from HTML", ("html_text",), ("links",)),
    "toml.parse": (toml_parse, "Parse TOML into JSON", ("toml_text",), ("json_text",)),
    "ini.parse": (ini_parse, "Parse INI sections into JSON", ("ini_text",), ("json_text",)),
    "markdown.headings": (markdown_headings, "Extract ATX Markdown headings", ("text",), ("headings",)),
}


def bootstrap_extras(registry: CapabilityRegistry) -> None:
    """Admit each extra capability once; new names can be added later."""
    for name, (func, description, inputs, outputs) in EXTRAS.items():
        if registry.get(name) is not None:
            continue
        registry.register(
            Capability(
                name=name,
                description=description,
                inputs=inputs,
                outputs=outputs,
                kind="builtin",
                entry=f"sovereign.extras:{func.__name__}",
                provenance=Provenance(source="builtin", url="", license="internal", confidence=1.0),
            ),
            version=1,
        )
