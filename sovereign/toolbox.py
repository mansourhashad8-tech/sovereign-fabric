"""Broad deterministic toolbox: encodings, data, math, dates, validation, graphs.

Every function is pure, bounded, and performs no network I/O. These capabilities
extend the fabric's execution surface without claiming capabilities it does not
have. Each takes a payload dict and returns ``{"value": ...}``.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import csv
import hashlib
import io
import ipaddress
import json
import math
import re
import unicodedata
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from functools import reduce
from itertools import islice
from typing import Any

from .capabilities import CapabilityRegistry
from .models import Capability, Provenance

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _text(payload: dict[str, Any]) -> str:
    return str(payload.get("value", ""))


def _bounded(payload: dict[str, Any], name: str, default: int, cap: int) -> int:
    try:
        value = int(payload.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, cap))


def _numbers(payload: dict[str, Any]) -> list[float]:
    raw = payload.get("value")
    if isinstance(raw, str):
        raw = re.split(r"[\s,;]+", raw.strip())
    if not isinstance(raw, (list, tuple)) or len(raw) > 10000:
        raise ValueError("value must be a list of at most 10000 numbers")
    numbers: list[float] = []
    for item in raw:
        try:
            number = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"non-numeric item {item!r}") from exc
        if not math.isfinite(number):
            raise ValueError("numbers must be finite")
        numbers.append(number)
    if not numbers:
        raise ValueError("at least one number is required")
    return numbers


def _table(payload: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    value = payload.get("value")
    if not isinstance(value, dict):
        raise ValueError("table must be an object with columns and rows")
    columns = [str(item) for item in (value.get("columns") or [])]
    rows = [list(row) for row in (value.get("rows") or [])]
    if not columns:
        return columns, rows
    if len(rows) > 5000:
        raise ValueError("table exceeds 5000 rows")
    width = len(columns)
    rows = [(row + [""] * width)[:width] for row in rows]
    return columns, rows


def _table_result(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"value": {"columns": columns, "rows": rows, "rows_count": len(rows)}}


def hash_sha512(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": hashlib.sha512(_text(payload).encode("utf-8")).hexdigest()}


def hex_encode(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": _text(payload).encode("utf-8").hex()}


def hex_decode(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip()
    if len(text) % 2 or len(text) > 20000:
        raise ValueError("hex input must have even length and at most 20000 characters")
    try:
        return {"value": bytes.fromhex(text).decode("utf-8")}
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid hex or non-UTF-8 bytes") from exc


def url_encode(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": urllib.parse.quote(_text(payload), safe="")}


def url_decode(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": urllib.parse.unquote(_text(payload))}


def base32_encode(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": base64.b32encode(_text(payload).encode("utf-8")).decode("ascii")}


def base32_decode(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return {"value": base64.b32decode(_text(payload).strip().upper()).decode("utf-8")}
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("invalid base32 or non-UTF-8 bytes") from exc


def json_flatten(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        body = json.loads(_text(payload))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc
    flat: dict[str, Any] = {}

    def walk(value: Any, prefix: str) -> None:
        if len(flat) >= 2000:
            raise ValueError("flattened JSON exceeds 2000 leaves")
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{prefix}.{key}" if prefix else str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}.{index}" if prefix else str(index))
        else:
            flat[prefix] = value

    walk(body, "")
    return {"value": flat, "leaves": len(flat)}


def json_paths(payload: dict[str, Any]) -> dict[str, Any]:
    flat = json_flatten(payload)["value"]
    return {"value": sorted(flat), "paths": len(flat)}


def json_merge(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        base = json.loads(_text(payload))
        patch = payload.get("patch")
        if isinstance(patch, str):
            patch = json.loads(patch)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(patch, dict):
        raise ValueError("patch must be a JSON object")
    if not isinstance(base, dict):
        base = {}
    merged = dict(base)

    def apply(target: dict[str, Any], source: dict[str, Any], depth: int = 0) -> None:
        if depth > 20:
            raise ValueError("merge depth exceeds 20")
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                apply(target[key], value, depth + 1)
            else:
                target[key] = value

    apply(merged, patch)
    return {"value": json.dumps(merged, ensure_ascii=False, sort_keys=True)}


def csv_columns(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("CSV input exceeds 200000 characters")
    rows = list(islice(csv.reader(io.StringIO(text)), 2))
    if not rows:
        return {"value": [], "columns": 0}
    if len(rows[0]) > 50:
        raise ValueError("CSV exceeds 50 columns")
    return {"value": rows[0], "columns": len(rows[0])}


def csv_select(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 200_000:
        raise ValueError("CSV input exceeds 200000 characters")
    rows = list(islice(csv.reader(io.StringIO(text)), 1001))
    if not rows:
        return {"value": ""}
    header = rows[0]
    wanted = payload.get("columns")
    if not isinstance(wanted, list) or not wanted:
        raise ValueError("columns must be a non-empty list")
    indexes: list[int] = []
    for name in wanted:
        if name not in header:
            raise ValueError(f"unknown column {name!r}")
        indexes.append(header.index(name))
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([header[index] for index in indexes])
    for row in rows[1:]:
        writer.writerow([row[index] if index < len(row) else "" for index in indexes])
    return {"value": out.getvalue(), "rows": len(rows) - 1}


def table_unique(payload: dict[str, Any]) -> dict[str, Any]:
    columns, rows = _table(payload)
    if not columns:
        return _table_result(columns, rows)
    column = payload.get("column", 0)
    index = columns.index(column) if isinstance(column, str) and column in columns else int(column)
    seen: set[str] = set()
    kept: list[list[Any]] = []
    for row in rows:
        key = str(row[index])
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return _table_result(columns, kept)


def table_limit(payload: dict[str, Any]) -> dict[str, Any]:
    columns, rows = _table(payload)
    limit = _bounded(payload, "n", 10, 1000)
    return _table_result(columns, rows[:limit])


def math_percent(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        value = float(payload.get("value"))
        total = float(payload.get("total"))
    except (TypeError, ValueError) as exc:
        raise ValueError("value and total must be numeric") from exc
    if total == 0:
        raise ValueError("total must be non-zero")
    return {"value": round(value / total * 100.0, 6), "percent": True}


def math_percentile(payload: dict[str, Any]) -> dict[str, Any]:
    numbers = sorted(_numbers(payload))
    try:
        p = float(payload.get("p", 50))
    except (TypeError, ValueError) as exc:
        raise ValueError("p must be numeric") from exc
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")
    index = max(0, min(len(numbers) - 1, math.ceil(p / 100 * len(numbers)) - 1))
    return {"value": numbers[index], "p": p, "count": len(numbers)}


def math_gcd(payload: dict[str, Any]) -> dict[str, Any]:
    values = [int(round(item)) for item in _numbers(payload)]
    return {"value": reduce(math.gcd, (abs(item) for item in values))}


def math_lcm(payload: dict[str, Any]) -> dict[str, Any]:
    values = [int(round(item)) for item in _numbers(payload)]
    result = 1
    for item in values:
        result = abs(result * item) // math.gcd(result, item)
    return {"value": result}


def math_primes(payload: dict[str, Any]) -> dict[str, Any]:
    limit = _bounded(payload, "limit", 100, 10000)
    if limit < 2:
        return {"value": [], "count": 0, "limit": limit}
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[:2] = b"\x00\x00"
    for number in range(2, int(limit**0.5) + 1):
        if sieve[number]:
            sieve[number * number : limit + 1 : number] = b"\x00" * (
                (limit - number * number) // number + 1
            )
    primes = [index for index, flag in enumerate(sieve) if flag]
    return {"value": primes, "count": len(primes), "limit": limit}


def math_base_convert(payload: dict[str, Any]) -> dict[str, Any]:
    raw = str(payload.get("value", "")).strip()
    text = raw.lstrip("+-").lower()
    try:
        from_base = int(payload.get("from_base", 10))
        to_base = int(payload.get("to_base", 10))
        number = int(text, from_base)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid number or base") from exc
    if not (2 <= from_base <= 36 and 2 <= to_base <= 36):
        raise ValueError("bases must be between 2 and 36")
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    sign = "-" if raw.startswith("-") else ""
    if number == 0:
        return {"value": "0", "from_base": from_base, "to_base": to_base}
    out: list[str] = []
    while number:
        number, remainder = divmod(number, to_base)
        out.append(digits[remainder])
    return {"value": sign + "".join(reversed(out)), "from_base": from_base, "to_base": to_base}


def date_iso_week(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        value = date.fromisoformat(_text(payload).strip())
    except ValueError as exc:
        raise ValueError("date must be ISO YYYY-MM-DD") from exc
    year, week, weekday = value.isocalendar()
    return {"value": {"year": year, "week": week, "weekday": weekday}, "iso": value.isoformat()}


def date_business_days(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("value")
    if isinstance(raw, list) and len(raw) == 2:
        start_text, end_text = raw
    else:
        start_text, end_text = payload.get("start"), payload.get("end")
    try:
        start = date.fromisoformat(str(start_text))
        end = date.fromisoformat(str(end_text))
    except (TypeError, ValueError) as exc:
        raise ValueError("start and end must be ISO dates") from exc
    if end < start:
        start, end = end, start
    if (end - start).days > 3660:
        raise ValueError("range exceeds 3660 days")
    holidays = set()
    for item in payload.get("holidays") or []:
        try:
            holidays.add(date.fromisoformat(str(item)))
        except ValueError:
            continue
    count = 0
    cursor = start
    while cursor < end:
        if cursor.weekday() < 5 and cursor not in holidays:
            count += 1
        cursor += timedelta(days=1)
    return {"value": count, "start": start.isoformat(), "end": end.isoformat()}


def text_slugify(payload: dict[str, Any]) -> dict[str, Any]:
    text = unicodedata.normalize("NFKC", _text(payload)).casefold()
    text = re.sub(r"[^\w]+", "-", text, flags=re.UNICODE).strip("-_")
    return {"value": text[:200]}


def text_rot13(payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": codecs.decode(_text(payload), "rot_13")}


def text_palindrome(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = re.sub(r"[^\w]", "", _text(payload).casefold())
    return {"value": normalized == normalized[::-1], "length": len(normalized)}


def text_levenshtein(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("value")
    if isinstance(raw, list) and len(raw) == 2:
        left, right = str(raw[0]), str(raw[1])
    else:
        left, right = str(payload.get("a", "")), str(payload.get("b", ""))
    if len(left) > 1000 or len(right) > 1000:
        raise ValueError("strings exceed 1000 characters")
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return {"value": previous[-1], "left": len(left), "right": len(right)}


def email_validate(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload).strip()
    valid = len(text) <= 254 and bool(_EMAIL.match(text))
    local, _, domain = text.partition("@")
    return {"value": {"valid": valid, "local_length": len(local), "domain": domain}}


def ip_validate(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        address = ipaddress.ip_address(_text(payload).strip())
    except ValueError:
        return {"value": {"valid": False}}
    return {
        "value": {
            "valid": True,
            "version": address.version,
            "private": address.is_private,
            "loopback": address.is_loopback,
            "global": address.is_global,
        }
    }


def credit_card_luhn(payload: dict[str, Any]) -> dict[str, Any]:
    digits = re.sub(r"\D", "", _text(payload))
    if not 12 <= len(digits) <= 19:
        return {"value": {"valid": False, "reason": "length"}}
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    brands = (
        ("4", "visa"),
        ("51", "mastercard"),
        ("52", "mastercard"),
        ("53", "mastercard"),
        ("54", "mastercard"),
        ("55", "mastercard"),
        ("34", "amex"),
        ("37", "amex"),
        ("6011", "discover"),
        ("65", "discover"),
    )
    brand = next((name for prefix, name in brands if digits.startswith(prefix)), "unknown")
    return {"value": {"valid": total % 10 == 0, "brand": brand, "last4": digits[-4:]}}


def password_entropy(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 1000:
        raise ValueError("password exceeds 1000 characters")
    alphabet = len(set(text))
    bits = len(text) * math.log2(alphabet) if alphabet > 1 else 0.0
    return {
        "value": {"entropy_bits": round(bits, 3), "length": len(text), "distinct": alphabet},
        "note": "entropy estimate only; not a strength guarantee",
    }


def set_operation(payload: dict[str, Any]) -> dict[str, Any]:
    left = payload.get("a") or []
    right = payload.get("b") or []
    if not isinstance(left, list) or not isinstance(right, list):
        raise ValueError("a and b must be lists")
    if len(left) > 1000 or len(right) > 1000:
        raise ValueError("sets exceed 1000 items")
    op = str(payload.get("op", "union")).lower()
    a, b = set(map(str, left)), set(map(str, right))
    if op == "union":
        result = a | b
    elif op == "intersection":
        result = a & b
    elif op == "difference":
        result = a - b
    elif op == "symmetric_difference":
        result = a ^ b
    else:
        raise ValueError("op must be union, intersection, difference, or symmetric_difference")
    return {"value": sorted(result), "op": op, "count": len(result)}


def graph_components(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("value") if isinstance(payload.get("value"), dict) else payload
    edges = body.get("edges") or []
    if not isinstance(edges, list) or len(edges) > 2000:
        raise ValueError("edges must be a list of at most 2000 items")
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if isinstance(edge, dict):
            source, target = str(edge.get("from")), str(edge.get("to"))
        else:
            source, target = str(edge[0]), str(edge[1])
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)
    seen: set[str] = set()
    groups: list[list[str]] = []
    for node in sorted(adjacency):
        if node in seen:
            continue
        stack, group = [node], []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            group.append(current)
            stack.extend(sorted(adjacency[current] - seen, reverse=True))
        groups.append(sorted(group))
    return {"value": groups, "components": len(groups), "nodes": len(adjacency)}


def graph_toposort(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("value") if isinstance(payload.get("value"), dict) else payload
    edges = body.get("edges") or []
    if not isinstance(edges, list) or len(edges) > 2000:
        raise ValueError("edges must be a list of at most 2000 items")
    nodes: set[str] = set()
    outgoing: dict[str, set[str]] = {}
    indegree: dict[str, int] = {}
    for edge in edges:
        if isinstance(edge, dict):
            source, target = str(edge.get("from")), str(edge.get("to"))
        else:
            source, target = str(edge[0]), str(edge[1])
        nodes.update((source, target))
        outgoing.setdefault(source, set()).add(target)
        indegree.setdefault(source, 0)
        indegree[target] = indegree.get(target, 0) + 1
    queue = sorted(node for node in nodes if indegree.get(node, 0) == 0)
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for target in sorted(outgoing.get(node, ())):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
        queue.sort()
    return {"value": order, "cycle": len(order) != len(nodes), "nodes": len(nodes)}


def xml_to_json(payload: dict[str, Any]) -> dict[str, Any]:
    text = _text(payload)
    if len(text) > 100_000:
        raise ValueError("XML input exceeds 100000 characters")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("invalid XML") from exc

    def convert(node: ET.Element, depth: int = 0) -> Any:
        if depth > 20:
            raise ValueError("XML depth exceeds 20")
        tag = node.tag.rsplit("}", 1)[-1]
        children = list(node)
        if not children:
            return {tag: (node.text or "").strip()}
        grouped: dict[str, Any] = {}
        for child in children:
            item = convert(child, depth + 1)
            child_tag = child.tag.rsplit("}", 1)[-1]
            value = item[child_tag]
            if child_tag in grouped:
                if not isinstance(grouped[child_tag], list):
                    grouped[child_tag] = [grouped[child_tag]]
                grouped[child_tag].append(value)
            else:
                grouped[child_tag] = value
        return {tag: grouped}

    return {"value": json.dumps(convert(root), ensure_ascii=False, sort_keys=True)}


def uuid_v5(payload: dict[str, Any]) -> dict[str, Any]:
    name = _text(payload)
    namespace = payload.get("namespace", "url")
    spaces = {"url": uuid.NAMESPACE_URL, "dns": uuid.NAMESPACE_DNS, "oid": uuid.NAMESPACE_OID}
    if namespace not in spaces:
        raise ValueError("namespace must be url, dns, or oid")
    return {"value": str(uuid.uuid5(spaces[namespace], name)), "namespace": namespace}


TOOLBOX: dict[str, tuple[Any, str, tuple[str, ...], tuple[str, ...]]] = {
    "hash.sha512": (hash_sha512, "SHA-512 digest of text", ("text",), ("digest",)),
    "hex.encode": (hex_encode, "Encode UTF-8 text as hex", ("text",), ("hex",)),
    "hex.decode": (hex_decode, "Decode hex bytes as UTF-8", ("hex",), ("text",)),
    "url.encode": (url_encode, "Percent-encode text for a URL component", ("text",), ("encoded",)),
    "url.decode": (url_decode, "Decode a percent-encoded URL component", ("encoded",), ("text",)),
    "base32.encode": (base32_encode, "Encode UTF-8 text as base32", ("text",), ("base32",)),
    "base32.decode": (base32_decode, "Decode base32 into UTF-8 text", ("base32",), ("text",)),
    "json.flatten": (json_flatten, "Flatten nested JSON into dotted paths (bounded)", ("json_text",), ("json_flattened",)),
    "json.paths": (json_paths, "List dotted leaf paths in a JSON document", ("json_text",), ("paths",)),
    "json.merge": (json_merge, "Recursively merge a JSON object patch", ("json_text",), ("json_text",)),
    "csv.columns": (csv_columns, "Read CSV header columns without parsing all rows", ("csv_text",), ("columns",)),
    "csv.select": (csv_select, "Select CSV columns and emit a bounded CSV", ("csv_text",), ("csv_text",)),
    "table.unique": (table_unique, "Remove duplicate table rows by one column", ("table",), ("table",)),
    "table.limit": (table_limit, "Limit a table to the first N rows", ("table",), ("table",)),
    "math.percent": (math_percent, "Percentage of a total", ("numbers",), ("percent",)),
    "math.percentile": (math_percentile, "Nearest-rank percentile of numeric values", ("math_values",), ("percentile",)),
    "math.gcd": (math_gcd, "Greatest common divisor of integers", ("math_values",), ("gcd",)),
    "math.lcm": (math_lcm, "Least common multiple of integers", ("math_values",), ("lcm",)),
    "math.primes": (math_primes, "Prime numbers up to a bounded limit", ("limit",), ("primes",)),
    "math.base_convert": (math_base_convert, "Convert an integer between bases 2 and 36", ("number_text",), ("converted",)),
    "date.iso_week": (date_iso_week, "ISO week and weekday for an ISO date", ("date",), ("iso_week",)),
    "date.business_days": (date_business_days, "Count weekdays between two ISO dates", ("dates",), ("business_days",)),
    "text.slugify": (text_slugify, "Unicode-aware slug with bounded length", ("text",), ("slug",)),
    "text.rot13": (text_rot13, "ROT13 transform", ("text",), ("text",)),
    "text.palindrome": (text_palindrome, "Check whether text is a palindrome ignoring punctuation", ("text",), ("palindrome_status",)),
    "text.levenshtein": (text_levenshtein, "Levenshtein edit distance for bounded strings", ("text_pair",), ("distance",)),
    "email.validate": (email_validate, "Structural email validation (no DNS lookup)", ("email",), ("email_status",)),
    "ip.validate": (ip_validate, "Validate an IP address and report its class flags", ("ip",), ("ip_status",)),
    "credit_card.luhn": (credit_card_luhn, "Luhn check with brand and last four digits only", ("card",), ("luhn_status",)),
    "password.entropy": (password_entropy, "Entropy estimate for a password (not a strength guarantee)", ("text",), ("entropy",)),
    "set.operation": (set_operation, "Union, intersection, difference, or symmetric difference", ("sets",), ("set_result",)),
    "graph.components": (graph_components, "Connected components of an undirected edge list", ("graph",), ("components",)),
    "graph.toposort": (graph_toposort, "Topological order or cycle detection", ("graph",), ("topological_order",)),
    "xml.to_json": (xml_to_json, "Convert bounded XML into JSON (no external entities)", ("xml_text",), ("json_text",)),
    "uuid.v5": (uuid_v5, "Deterministic UUIDv5 from a name and namespace", ("uuid_request",), ("uuid",)),
}


def bootstrap_toolbox(registry: CapabilityRegistry) -> None:
    """Admit the broad toolbox once; adding a function is a new capability."""
    for name, (func, description, inputs, outputs) in TOOLBOX.items():
        if registry.get(name) is not None:
            continue
        registry.register(
            Capability(
                name=name,
                description=description,
                inputs=inputs,
                outputs=outputs,
                kind="builtin",
                entry=f"sovereign.toolbox:{func.__name__}",
                provenance=Provenance(source="builtin", url="", license="internal", confidence=1.0),
            ),
            version=1,
        )
