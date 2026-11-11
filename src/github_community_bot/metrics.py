"""A tiny Prometheus-compatible metrics registry.

Prometheus client libraries are excellent but pull in a dependency and a global
registry. The bot only needs a handful of counters and gauges, so a small,
thread-safe implementation keeps deployments light and testable.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from collections.abc import Iterable


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    pairs = ",".join(f'{key}="{_escape_label(value)}"' for key, value in sorted(labels.items()))
    return "{" + pairs + "}"


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._started = time.monotonic()

    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            bucket = self._counters[name]
            bucket[key] = bucket.get(key, 0.0) + amount

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._gauges[name][key] = float(value)

    def get_counter(self, name: str, **labels: str) -> float:
        key = tuple(sorted(labels.items()))
        with self._lock:
            return self._counters.get(name, {}).get(key, 0.0)

    def _lines(
        self, name: str, kind: str, values: dict[tuple[tuple[str, str], ...], float]
    ) -> Iterable[str]:
        yield f"# TYPE {name} {kind}"
        for key, value in sorted(values.items()):
            labels = dict(key)
            rendered = f"{value:g}" if math.isfinite(value) else "0"
            yield f"{name}{_format_labels(labels)} {rendered}"

    def render(self) -> str:
        with self._lock:
            counters = {name: dict(values) for name, values in self._counters.items()}
            gauges = {name: dict(values) for name, values in self._gauges.items()}
            uptime = time.monotonic() - self._started

        gauges.setdefault("bot_uptime_seconds", {})[()] = uptime
        lines: list[str] = []
        for name, values in sorted(counters.items()):
            lines.extend(self._lines(name, "counter", values))
        for name, values in sorted(gauges.items()):
            lines.extend(self._lines(name, "gauge", values))
        return "\n".join(lines) + "\n"

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {
                f"{name}{_format_labels(dict(key))}": value
                for name, values in self._counters.items()
                for key, value in values.items()
            }
