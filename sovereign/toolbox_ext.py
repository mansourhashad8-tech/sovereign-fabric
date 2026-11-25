"""Extended deterministic toolbox: compression, statistics, math, dates, graphs.

All functions are pure, bounded, and perform no network I/O. Binary codecs return
base64 text so results stay JSON-safe.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import random
import re
import urllib.parse
import zlib
from collections import Counter
from datetime import date, timedelta
from typing import Any

from .capabilities import CapabilityRegistry
from .models import Capability, Provenance

_WORD = re.compile(r"[A-Za-z0-9\u0600-\u06FF]+")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def _text(payload: dict[str, Any]) -> str:
    return str(payload.get("value", ""))


def _numbers(payload: dict[str, Any]) -> list[float]:
    raw = payload.get("value")
    if not isinstance(raw, list) or not raw or len(raw) > 10000:
        raise ValueError("value must be a non-empty list of at most 10000 numbers")
    values: list[float] = []
    for item in raw:
        try:
            number = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("all values must be numeric") from exc
        if not math.isfinite(number):
            raise ValueError("values must be finite")
        values.append(number)
    return values


def _pair(payload: dict[str, Any]) -> tuple[list[float], list[float]]:
    left = payload.get("x")
    right = payload.get("y")
    if not isinstance(left, list) or not isinstance(right, list):
        raise ValueError("x and y must be lists")
    if len(left) != len(right) or len(left) < 2 or len(left) > 10000:
        raise ValueError("x and y must have equal length between 2 and 10000")
    return _numbers({"value": left}), _numbers({"value": right})


def _b64decode(payload: dict[str, Any], cap: int = 200_000) -> bytes:
    try:
        raw = base64.b64decode(_text(payload), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64") from exc
    if len(raw) > cap:
        raise ValueError(f"encoded input exceeds {cap} bytes")
    return raw


def _safe_decompress(raw: bytes, wbits: int) -> bytes:
    try:
        obj = zlib.decompressobj(wbits)
        out = obj.decompress(raw, 200_001)
        if len(out) > 200_000 or obj.unconsumed_tail:
            raise ValueError("decompressed output exceeds 200000 bytes")
        out += obj.flush()
    except zlib.error as exc:
        raise ValueError("invalid compressed data") from exc
    if len(out) > 200_000 or not obj.eof:
        raise ValueError("decompressed output exceeds 200000 bytes or is truncated")
    return out


def base85_encode(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": base64.b85encode(_text(payload).encode("utf-8")).decode("ascii")}


def base85_decode(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"value": base64.b85decode(_text(payload).strip()).decode("utf-8")}
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("invalid base85 or non-UTF-8 bytes") from exc


def zlib_compress(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _text(payload).encode("utf-8")
    if len(raw) > 200_000:
        raise ValueError("input exceeds 200000 bytes")
    return {"value": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}


def zlib_decompress(payload: dict[str, Any]) -> dict[str, Any]:
    out = _safe_decompress(_b64decode(payload), zlib.MAX_WBITS)
    return {"value": out.decode("utf-8"), "bytes": len(out)}


def gzip_compress(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _text(payload).encode("utf-8")
    if len(raw) > 200_000:
        raise ValueError("input exceeds 200000 bytes")
    compressor = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    packed = compressor.compress(raw) + compressor.flush()
    return {"value": base64.b64encode(packed).decode("ascii")}


def gzip_decompress(payload: dict[str, Any]) -> dict[str, Any]:
    out = _safe_decompress(_b64decode(payload), 16 + zlib.MAX_WBITS)
    return {"value": out.decode("utf-8"), "bytes": len(out)}


def stats_correlation(payload: dict[str, Any]) -> dict[str, Any]:
    x, y = _pair(payload)
    mx, my = sum(x) / len(x), sum(y) / len(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    if vx == 0 or vy == 0:
        raise ValueError("correlation is undefined when a series is constant")
    r = max(-1.0, min(1.0, cov / math.sqrt(vx * vy)))
    return {"value": round(r, 12), "n": len(x)}


def stats_linear_regression(payload: dict[str, Any]) -> dict[str, Any]:
    x, y = _pair(payload)
    mx, my = sum(x) / len(x), sum(y) / len(y)
    vx = sum((a - mx) ** 2 for a in x)
    if vx == 0:
        raise ValueError("x must not be constant")
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / vx
    intercept = my - slope * mx
    predicted = [slope * a + intercept for a in x]
    ss_res = sum((b - p) ** 2 for b, p in zip(y, predicted))
    ss_tot = sum((b - my) ** 2 for b in y)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    return {
        "value": {
            "slope": round(slope, 12),
            "intercept": round(intercept, 12),
            "r2": round(max(0.0, min(1.0, r2)), 12),
            "n": len(x),
        }
    }


def stats_zscore(payload: dict[str, Any]) -> dict[str, Any]:
    values = _numbers(payload)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    if variance == 0:
        return {"value": [0.0] * len(values), "mean": mean, "stdev": 0.0}
    stdev = math.sqrt(variance)
    return {
        "value": [round((value - mean) / stdev, 12) for value in values],
        "mean": round(mean, 12),
        "stdev": round(stdev, 12),
    }


def stats_bootstrap_ci(payload: dict[str, Any]) -> dict[str, Any]:
    values = _numbers(payload)
    try:
        resamples = int(payload.get("resamples", 1000))
        seed = int(payload.get("seed", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("resamples and seed must be integers") from exc
    resamples = max(10, min(resamples, 5000))
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        sample = [rng.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    low = means[max(0, int(0.025 * resamples) - 1)]
    high = means[min(resamples - 1, int(0.975 * resamples))]
    return {
        "value": {"mean": round(sum(values) / len(values), 12), "low": round(low, 12), "high": round(high, 12)},
        "resamples": resamples,
        "seed": seed,
        "note": "percentile bootstrap; deterministic for a fixed seed",
    }


def stats_moving_average(payload: dict[str, Any]) -> dict[str, Any]:
    values = _numbers(payload)
    try:
        window = int(payload.get("window", 3))
    except (TypeError, ValueError) as exc:
        raise ValueError("window must be an integer") from exc
    if not 1 <= window <= len(values):
        raise ValueError("window must be between 1 and the number of values")
    result = [
        round(sum(values[index : index + window]) / window, 12)
        for index in range(len(values) - window + 1)
    ]
    return {"value": result, "window": window}


def stats_histogram(payload: dict[str, Any]) -> dict[str, Any]:
    values = _numbers(payload)
    try:
        bins = int(payload.get("bins", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("bins must be an integer") from exc
    bins = max(1, min(bins, 50))
    low, high = min(values), max(values)
    if low == high:
        raise ValueError("histogram needs at least two distinct values")
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, int((value - low) / width))
        counts[index] += 1
    edges = [round(low + index * width, 12) for index in range(bins + 1)]
    return {"value": {"counts": counts, "edges": edges}, "bins": bins}


def _integer(payload: dict[str, Any], name: str = "value") -> int:
    try:
        return int(payload.get(name))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def math_factorial(payload: dict[str, Any]) -> dict[str, Any]:
    n = _integer(payload)
    if not 0 <= n <= 500:
        raise ValueError("n must be between 0 and 500")
    return {"value": math.factorial(n), "n": n}


def math_combinations(payload: dict[str, Any]) -> dict[str, Any]:
    n, k = _integer(payload, "n"), _integer(payload, "k")
    if not 0 <= k <= n <= 1000:
        raise ValueError("require 0 <= k <= n <= 1000")
    return {"value": math.comb(n, k), "n": n, "k": k}


def math_fibonacci(payload: dict[str, Any]) -> dict[str, Any]:
    n = _integer(payload)
    if not 0 <= n <= 1000:
        raise ValueError("n must be between 0 and 1000")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return {"value": a, "n": n}


def math_is_prime(payload: dict[str, Any]) -> dict[str, Any]:
    n = _integer(payload)
    if n < 2:
        return {"value": False, "n": n}
    for prime in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % prime == 0:
            return {"value": n == prime, "n": n}
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for base in (2, 3, 5, 7, 11, 13, 17):
        x = pow(base, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return {"value": False, "n": n}
    return {"value": True, "n": n}


def math_totient(payload: dict[str, Any]) -> dict[str, Any]:
    n = _integer(payload)
    if not 1 <= n <= 10**12:
        raise ValueError("n must be between 1 and 10^12")
    remaining, result, factor = n, n, 2
    while factor * factor <= remaining:
        if remaining % factor == 0:
            while remaining % factor == 0:
                remaining //= factor
            result -= result // factor
        factor += 1 if factor == 2 else 2
    if remaining > 1:
        result -= result // remaining
    return {"value": result, "n": n}


def math_modinv(payload: dict[str, Any]) -> dict[str, Any]:
    a, modulus = _integer(payload, "a"), _integer(payload, "m")
    if modulus <= 1:
        raise ValueError("m must be greater than 1")
    try:
        inverse = pow(a, -1, modulus)
    except ValueError as exc:
        raise ValueError("a and m are not coprime") from exc
    return {"value": inverse, "a": a, "m": modulus}


def _iso_date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("dates must be ISO YYYY-MM-DD") from exc


def date_add_business_days(payload: dict[str, Any]) -> dict[str, Any]:
    start = _iso_date(_text(payload))
    try:
        days = int(payload.get("days", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("days must be an integer") from exc
    if not -3660 <= days <= 3660:
        raise ValueError("days must be between -3660 and 3660")
    holidays = set()
    for item in payload.get("holidays") or []:
        try:
            holidays.add(_iso_date(item))
        except ValueError:
            continue
    cursor = start
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    while remaining:
        cursor += timedelta(days=step)
        if cursor.weekday() < 5 and cursor not in holidays:
            remaining -= 1
    return {"value": cursor.isoformat(), "start": start.isoformat(), "days": days}


def date_range(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("value")
    if isinstance(raw, list) and len(raw) == 2:
        start_text, end_text = raw
    else:
        start_text, end_text = payload.get("start"), payload.get("end")
    start, end = _iso_date(start_text), _iso_date(end_text)
    if end < start:
        raise ValueError("end must not precede start")
    if (end - start).days > 3660:
        raise ValueError("range exceeds 3660 days")
    return {
        "value": [
            (start + timedelta(days=offset)).isoformat()
            for offset in range((end - start).days + 1)
        ],
        "days": (end - start).days + 1,
    }


def geo_haversine(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        lat1 = float(payload.get("lat1"))
        lon1 = float(payload.get("lon1"))
        lat2 = float(payload.get("lat2"))
        lon2 = float(payload.get("lon2"))
    except (TypeError, ValueError) as exc:
        raise ValueError("lat1, lon1, lat2, and lon2 must be numeric") from exc
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("latitudes must be between -90 and 90")
    if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("longitudes must be between -180 and 180")
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    km = 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(a)))
    return {"value": round(km, 6), "unit": "km", "earth_radius_km": 6371.0088}


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        raise ValueError("color must be #rgb or #rrggbb")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))


def color_hex_to_rgb(payload: dict[str, Any]) -> dict[str, Any]:
    r, g, b = _rgb(_text(payload))
    return {"value": {"r": r, "g": g, "b": b}, "hex": f"#{r:02x}{g:02x}{b:02x}"}


def _luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for channel in rgb:
        value = channel / 255.0
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def color_contrast_ratio(payload: dict[str, Any]) -> dict[str, Any]:
    first, second = _text(payload).split(",") if "," in _text(payload) else (None, None)
    if first is None:
        first, second = payload.get("a"), payload.get("b")
    l1, l2 = _luminance(_rgb(str(first))), _luminance(_rgb(str(second)))
    ratio = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
    return {
        "value": round(ratio, 6),
        "wcag_aa_normal": ratio >= 4.5,
        "wcag_aaa_normal": ratio >= 7.0,
    }


def bits_popcount(payload: dict[str, Any]) -> dict[str, Any]:
    n = _integer(payload)
    if n < 0 or n.bit_length() > 10000:
        raise ValueError("n must be non-negative and at most 10000 bits")
    return {"value": n.bit_count(), "bits": n.bit_length()}


def bits_xor(payload: dict[str, Any]) -> dict[str, Any]:
    a, b = _integer(payload, "a"), _integer(payload, "b")
    if a < 0 or b < 0 or max(a, b).bit_length() > 10000:
        raise ValueError("a and b must be non-negative and at most 10000 bits")
    result = a ^ b
    return {"value": result, "hex": hex(result)}


def url_validate(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip()
    if len(text) > 2000:
        return {"value": {"valid": False, "reason": "length"}}
    try:
        parts = urllib.parse.urlsplit(text)
        port = parts.port
    except ValueError:
        return {"value": {"valid": False, "reason": "parse"}}
    valid = parts.scheme in {"http", "https"} and bool(parts.hostname)
    return {
        "value": {
            "valid": valid,
            "scheme": parts.scheme,
            "host": parts.hostname or "",
            "port": port,
            "path": parts.path[:500],
        }
    }


def domain_validate(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip().rstrip(".").lower()
    if not text or len(text) > 253:
        return {"value": {"valid": False, "reason": "length"}}
    labels = text.split(".")
    if len(labels) < 2 or len(labels[-1]) < 2 or not labels[-1].isalpha():
        return {"value": {"valid": False, "reason": "tld"}}
    if any(not 1 <= len(label) <= 63 or not _LABEL.fullmatch(label) for label in labels):
        return {"value": {"valid": False, "reason": "label"}}
    try:
        ascii_name = text.encode("idna").decode("ascii")
    except UnicodeError:
        return {"value": {"valid": False, "reason": "idna"}}
    return {"value": {"valid": True, "ascii": ascii_name, "labels": len(labels)}}


def text_readability(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 100_000:
        raise ValueError("text exceeds 100000 characters")
    sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not sentences or not words:
        raise ValueError("readability needs sentences and English words")

    def syllables(word: str) -> int:
        groups = re.findall(r"[aeiouy]+", word.lower())
        return max(1, len(groups))

    total_syllables = sum(syllables(word) for word in words)
    score = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (total_syllables / len(words))
    return {
        "value": {
            "flesch_reading_ease": round(score, 3),
            "sentences": len(sentences),
            "words": len(words),
            "syllables": total_syllables,
        },
        "note": "English Flesch approximation; not a general readability proof",
    }


def text_word_frequency(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("text exceeds 200000 characters")
    try:
        top = int(payload.get("top", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("top must be an integer") from exc
    top = max(1, min(top, 100))
    counts = Counter(_WORD.findall(text.casefold()))
    return {
        "value": [
            {"word": word, "count": count} for word, count in counts.most_common(top)
        ],
        "unique": len(counts),
        "total": sum(counts.values()),
    }


def _graph_edges(payload: dict[str, Any]) -> list[tuple[str, str]]:
    body = payload.get("value") if isinstance(payload.get("value"), dict) else payload
    edges = body.get("edges") or []
    if not isinstance(edges, list) or len(edges) > 2000:
        raise ValueError("edges must be a list of at most 2000 items")
    parsed: list[tuple[str, str]] = []
    for edge in edges:
        if isinstance(edge, dict):
            source, target = edge.get("from"), edge.get("to")
        elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
            source, target = edge[0], edge[1]
        else:
            raise ValueError("each edge must be an object or a 2-item list")
        if source is None or target is None:
            raise ValueError("each edge needs from/to endpoints")
        parsed.append((str(source), str(target)))
    return parsed


def graph_degree_centrality(payload: dict[str, Any]) -> dict[str, Any]:
    edges = _graph_edges(payload)
    nodes: set[str] = set()
    degree: Counter[str] = Counter()
    for source, target in edges:
        nodes.update((source, target))
        degree[source] += 1
        degree[target] += 1
    denominator = max(1, len(nodes) - 1)
    return {
        "value": {node: round(degree[node] / denominator, 12) for node in sorted(nodes)},
        "nodes": len(nodes),
        "edges": len(edges),
    }


def graph_clustering_coefficient(payload: dict[str, Any]) -> dict[str, Any]:
    edges = _graph_edges(payload)
    adjacency: dict[str, set[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    coefficients: dict[str, float] = {}
    for node, neighbours in adjacency.items():
        degree = len(neighbours)
        if degree < 2:
            coefficients[node] = 0.0
            continue
        links = 0
        for other in neighbours:
            links += len(adjacency[other] & neighbours)
        coefficients[node] = round(links / (degree * (degree - 1)), 12)
    average = sum(coefficients.values()) / len(coefficients) if coefficients else 0.0
    return {
        "value": {"nodes": coefficients, "average": round(average, 12)},
        "nodes": len(adjacency),
    }


def graph_edge_density(payload: dict[str, Any]) -> dict[str, Any]:
    edges = _graph_edges(payload)
    directed = bool(payload.get("directed", False))
    nodes: set[str] = set()
    for source, target in edges:
        nodes.update((source, target))
    count = len(nodes)
    if count < 2:
        raise ValueError("density needs at least two nodes")
    unique_edges = len(set(edges))
    possible = count * (count - 1) if directed else count * (count - 1) / 2
    return {
        "value": round(unique_edges / possible, 12),
        "nodes": count,
        "edges": unique_edges,
        "directed": directed,
    }


def json_pointer(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("JSON exceeds 200000 characters")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc
    pointer = payload.get("pointer")
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("pointer must be empty or start with /")
    current = document
    for raw in pointer.split("/")[1:] if pointer else []:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"pointer token {token!r} not found")
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
                current = current[index]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"invalid array index {token!r}") from exc
        else:
            raise ValueError("pointer descends into a scalar")
    return {"value": current}


def json_merge_patch(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        target = json.loads(_text(payload))
        patch = payload.get("patch")
        if isinstance(patch, str):
            patch = json.loads(patch)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc

    def apply(current: Any, change: Any, depth: int = 0) -> Any:
        if depth > 20:
            raise ValueError("merge depth exceeds 20")
        if not isinstance(change, dict):
            return change
        base = dict(current) if isinstance(current, dict) else {}
        for key, value in change.items():
            if value is None:
                base.pop(key, None)
            else:
                base[key] = apply(base.get(key), value, depth + 1)
        return base

    return {"value": json.dumps(apply(target, patch), ensure_ascii=False, sort_keys=True)}


def hash_crc32(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": zlib.crc32(_text(payload).encode("utf-8")) & 0xFFFFFFFF}


def hash_adler32(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": zlib.adler32(_text(payload).encode("utf-8")) & 0xFFFFFFFF}


TOOLBOX_EXT: dict[str, tuple[Any, str, tuple[str, ...], tuple[str, ...]]] = {
    "base85.encode": (base85_encode, "Encode UTF-8 text as base85", ("text",), ("base85",)),
    "base85.decode": (base85_decode, "Decode base85 into UTF-8 text", ("base85",), ("text",)),
    "zlib.compress": (zlib_compress, "zlib-compress text into base64", ("text",), ("base64",)),
    "zlib.decompress": (zlib_decompress, "Decompress bounded zlib base64", ("base64",), ("text",)),
    "gzip.compress": (gzip_compress, "gzip-compress text into base64", ("text",), ("base64",)),
    "gzip.decompress": (gzip_decompress, "Decompress bounded gzip base64", ("base64",), ("text",)),
    "stats.correlation": (stats_correlation, "Pearson correlation of two series", ("series",), ("correlation",)),
    "stats.linear_regression": (stats_linear_regression, "Ordinary least-squares line and R-squared", ("series",), ("regression",)),
    "stats.zscore": (stats_zscore, "Population z-scores", ("numbers",), ("zscores",)),
    "stats.bootstrap_ci": (stats_bootstrap_ci, "Seeded percentile bootstrap confidence interval", ("numbers",), ("confidence_interval",)),
    "stats.moving_average": (stats_moving_average, "Trailing moving average", ("numbers",), ("moving_average",)),
    "stats.histogram": (stats_histogram, "Bounded histogram counts and edges", ("numbers",), ("histogram",)),
    "math.factorial": (math_factorial, "Factorial up to 500", ("n",), ("integer",)),
    "math.combinations": (math_combinations, "Binomial coefficient n choose k", ("n",), ("integer",)),
    "math.fibonacci": (math_fibonacci, "Fibonacci number up to n=1000", ("n",), ("integer",)),
    "math.is_prime": (math_is_prime, "Deterministic Miller-Rabin primality test", ("n",), ("boolean",)),
    "math.totient": (math_totient, "Euler totient up to 10^12", ("n",), ("integer",)),
    "math.modinv": (math_modinv, "Modular inverse when it exists", ("a",), ("integer",)),
    "date.add_business_days": (date_add_business_days, "Shift an ISO date by weekdays", ("date",), ("date",)),
    "date.range": (date_range, "Inclusive ISO date range, bounded", ("dates",), ("dates",)),
    "geo.haversine": (geo_haversine, "Great-circle distance in kilometres", ("coordinates",), ("distance_km",)),
    "color.hex_to_rgb": (color_hex_to_rgb, "Hex color to RGB channels", ("hex_color",), ("rgb",)),
    "color.contrast_ratio": (color_contrast_ratio, "WCAG relative-luminance contrast ratio", ("colors",), ("contrast",)),
    "bits.popcount": (bits_popcount, "Number of set bits", ("integer",), ("count",)),
    "bits.xor": (bits_xor, "Bitwise XOR of two non-negative integers", ("integers",), ("integer",)),
    "url.validate": (url_validate, "Structural http(s) URL validation (no fetch)", ("url",), ("url_status",)),
    "domain.validate": (domain_validate, "DNS-label and IDNA domain validation (no lookup)", ("domain",), ("domain_status",)),
    "text.readability": (text_readability, "English Flesch reading-ease approximation", ("text",), ("readability",)),
    "text.word_frequency": (text_word_frequency, "Top word frequencies", ("text",), ("frequencies",)),
    "graph.degree_centrality": (graph_degree_centrality, "Degree centrality of an edge list", ("graph",), ("centrality",)),
    "graph.clustering_coefficient": (graph_clustering_coefficient, "Local and average clustering coefficients", ("graph",), ("clustering",)),
    "graph.edge_density": (graph_edge_density, "Directed or undirected edge density", ("graph",), ("density",)),
    "json.pointer": (json_pointer, "Resolve an RFC 6901 JSON pointer", ("json_text",), ("json_value",)),
    "json.merge_patch": (json_merge_patch, "Apply an RFC 7386 JSON merge patch", ("json_text",), ("json_text",)),
    "hash.crc32": (hash_crc32, "CRC-32 checksum", ("text",), ("checksum",)),
    "hash.adler32": (hash_adler32, "Adler-32 checksum", ("text",), ("checksum",)),
}


def bootstrap_toolbox_ext(registry: CapabilityRegistry) -> None:
    for name, (func, description, inputs, outputs) in TOOLBOX_EXT.items():
        if registry.get(name) is not None:
            continue
        registry.register(
            Capability(
                name=name,
                description=description,
                inputs=inputs,
                outputs=outputs,
                kind="builtin",
                entry=f"sovereign.toolbox_ext:{func.__name__}",
                provenance=Provenance(source="builtin", url="", license="internal", confidence=1.0),
            ),
            version=1,
        )
