"""Agregador leve e thread-safe de métricas de execução."""

from __future__ import annotations

import threading
from collections import defaultdict
from statistics import mean
from typing import Any

from challenge.logging_setup import SCHEMA_VERSION


def _percentile(values: list[float], quantile: float) -> float | None:
    """Calcula percentil nearest-rank para uma amostra não vazia."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return round(ordered[index], 3)


class MetricsRegistry:
    """Mantém contadores e distribuições, sem rótulos de alta cardinalidade."""

    def __init__(self) -> None:
        """Inicializa armazenamentos protegidos por lock."""
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._observations: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: float = 1.0) -> None:
        """Incrementa um contador nomeado."""
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, value: float) -> None:
        """Adiciona uma observação numérica para análise de distribuição."""
        with self._lock:
            self._observations[name].append(float(value))

    def snapshot(self) -> dict[str, Any]:
        """Retorna contadores e percentis para serialização JSON."""
        with self._lock:
            counters = dict(self._counters)
            observations = {name: list(values) for name, values in self._observations.items()}
        distributions = {}
        for name, values in observations.items():
            distributions[name] = {
                "count": len(values),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "mean": round(mean(values), 3),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
                "p99": _percentile(values, 0.99),
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "counters": {name: round(value, 3) for name, value in sorted(counters.items())},
            "distributions": distributions,
        }
