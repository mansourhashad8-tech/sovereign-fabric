"""In-process metrics for the HTTP surface.

Counters are monotonic for the life of the process. They are deliberately
simple: no external collector, no background thread, and no per-request
allocation beyond a short lock.
"""

from __future__ import annotations

import threading
from collections import Counter
from typing import Any


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests = 0
        self.statuses: Counter[str] = Counter()
        self.duration_sum = 0.0
        self.duration_max = 0.0
        self.rejections: Counter[str] = Counter()

    def observe(self, status: int, duration_s: float) -> None:
        with self._lock:
            self.requests += 1
            self.statuses[str(status)] += 1
            self.duration_sum += duration_s
            if duration_s > self.duration_max:
                self.duration_max = duration_s

    def reject(self, kind: str) -> None:
        with self._lock:
            self.rejections[kind] += 1

    def snapshot(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            data = {
                "requests": self.requests,
                "statuses": dict(self.statuses),
                "duration_sum": self.duration_sum,
                "duration_max": self.duration_max,
                "rejections": dict(self.rejections),
            }
        if extra:
            data.update(extra)
        return data

    def render(self, extra: dict[str, Any] | None = None) -> str:
        data = self.snapshot(extra)
        lines = [
            "# HELP sovereign_requests_total Total HTTP requests",
            "# TYPE sovereign_requests_total counter",
            f"sovereign_requests_total {data['requests']}",
            "# HELP sovereign_requests_by_status Requests grouped by status",
            "# TYPE sovereign_requests_by_status counter",
        ]
        for status, count in sorted(data["statuses"].items()):
            lines.append(f'sovereign_requests_by_status{{status="{status}"}} {count}')
        lines += [
            "# HELP sovereign_request_duration_seconds_sum Sum of request durations",
            "# TYPE sovereign_request_duration_seconds_sum counter",
            f"sovereign_request_duration_seconds_sum {data['duration_sum']:.6f}",
            "# HELP sovereign_request_duration_seconds_count Observed requests",
            "# TYPE sovereign_request_duration_seconds_count counter",
            f"sovereign_request_duration_seconds_count {data['requests']}",
            "# HELP sovereign_request_duration_seconds_max Maximum observed duration",
            "# TYPE sovereign_request_duration_seconds_max gauge",
            f"sovereign_request_duration_seconds_max {data['duration_max']:.6f}",
        ]
        for kind in ("rate_limit", "body_limit", "auth"):
            value = data["rejections"].get(kind, 0)
            lines += [
                f"# HELP sovereign_{kind}_rejections_total Rejected {kind} requests",
                f"# TYPE sovereign_{kind}_rejections_total counter",
                f"sovereign_{kind}_rejections_total {value}",
            ]
        for key in ("capabilities", "knowledge_units", "cycles", "optimizations", "feedback"):
            if key in data:
                lines += [
                    f"# HELP sovereign_{key} Current {key}",
                    f"# TYPE sovereign_{key} gauge",
                    f"sovereign_{key} {data[key]}",
                ]
        return "\n".join(lines) + "\n"
