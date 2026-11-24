"""Bounded graph algorithms over explicit edge lists.

The fabric graph stores provenance; these functions answer path and importance
questions over a caller-supplied graph without touching the store.
"""

from __future__ import annotations

import heapq
import math
from typing import Any

MAX_EDGES = 2000
MAX_NODES = 2000
MAX_ITERATIONS = 100


def _body(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("value")
    return value if isinstance(value, dict) else payload


def _edges(payload: dict[str, Any]) -> list[tuple[str, str, float]]:
    body = _body(payload)
    raw = body.get("edges")
    if not isinstance(raw, list) or len(raw) > MAX_EDGES:
        raise ValueError(f"edges must be a list of at most {MAX_EDGES} items")
    edges: list[tuple[str, str, float]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            source, target = item.get("from"), item.get("to")
            weight = item.get("weight", 1.0)
        elif isinstance(item, (list, tuple)) and len(item) in {2, 3}:
            source, target = item[0], item[1]
            weight = item[2] if len(item) == 3 else 1.0
        else:
            raise ValueError(f"edge {index} must be an object or a 2/3-item list")
        try:
            source, target = str(source), str(target)
            weight = float(weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"edge {index} has invalid endpoints or weight") from exc
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"edge {index} weight must be finite and non-negative")
        edges.append((source, target, weight))
    return edges


def shortest_path(payload: dict[str, Any]) -> dict[str, Any]:
    body = _body(payload)
    edges = _edges(payload)
    start, end = body.get("start"), body.get("end")
    if start is None or end is None:
        raise ValueError("start and end are required")
    start, end = str(start), str(end)
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for source, target, weight in edges:
        adjacency.setdefault(source, []).append((target, weight))
        adjacency.setdefault(target, [])
    if start not in adjacency or end not in adjacency:
        raise ValueError("start or end is not present in the edge list")
    distances = {node: math.inf for node in adjacency}
    previous: dict[str, str | None] = {node: None for node in adjacency}
    distances[start] = 0.0
    queue: list[tuple[float, str]] = [(0.0, start)]
    visited: list[str] = []
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances[node]:
            continue
        visited.append(node)
        if node == end:
            break
        for target, weight in adjacency[node]:
            candidate = distance + weight
            if candidate < distances[target]:
                distances[target] = candidate
                previous[target] = node
                heapq.heappush(queue, (candidate, target))
    if not math.isfinite(distances[end]):
        raise ValueError(f"no path from {start!r} to {end!r}")
    path = [end]
    while path[-1] != start:
        parent = previous[path[-1]]
        if parent is None:
            raise ValueError("path reconstruction failed")
        path.append(parent)
    path.reverse()
    return {
        "value": {
            "path": path,
            "distance": round(distances[end], 12),
            "visited": visited,
            "nodes": len(adjacency),
            "edges": len(edges),
        }
    }


def pagerank(payload: dict[str, Any]) -> dict[str, Any]:
    body = _body(payload)
    edges = _edges(payload)
    damping = float(body.get("damping", 0.85))
    iterations = int(body.get("iterations", 30))
    if not 0 < damping < 1:
        raise ValueError("damping must be between 0 and 1")
    if not 1 <= iterations <= MAX_ITERATIONS:
        raise ValueError(f"iterations must be from 1 to {MAX_ITERATIONS}")
    nodes = {source for source, _, _ in edges} | {target for _, target, _ in edges}
    extra = body.get("nodes")
    if extra is not None:
        if not isinstance(extra, list):
            raise ValueError("nodes must be a list")
        nodes |= {str(node) for node in extra}
    if not nodes:
        raise ValueError("no nodes supplied")
    if len(nodes) > MAX_NODES:
        raise ValueError(f"too many nodes (limit {MAX_NODES})")
    outgoing: dict[str, list[str]] = {node: [] for node in nodes}
    incoming: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target, _ in edges:
        outgoing[source].append(target)
        incoming[target].append(source)
    count = len(nodes)
    ranks = {node: 1.0 / count for node in nodes}
    for _ in range(iterations):
        dangling = sum(ranks[node] for node in nodes if not outgoing[node])
        updated = {}
        for node in nodes:
            total = sum(ranks[parent] / len(outgoing[parent]) for parent in incoming[node])
            updated[node] = (1 - damping) / count + damping * (total + dangling / count)
        ranks = updated
    total_rank = sum(ranks.values())
    return {
        "value": {
            "nodes": count,
            "edges": len(edges),
            "iterations": iterations,
            "damping": damping,
            "scores": {node: round(ranks[node] / total_rank, 12) for node in sorted(nodes)},
        }
    }
