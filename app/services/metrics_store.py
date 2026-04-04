from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class QueryMetrics:
    query: str
    entity_type: str
    stage_timings: Dict[str, float]        # e.g. {"search": 1.2, "scrape": 8.4, ...}
    search_results_count: int
    pages_scraped: int
    pages_failed: int
    entities_raw: int
    entities_final: int
    evidence_total: int
    evidence_verified: int                 # evidence cells that are real substrings of page text
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    total_time: float
    timestamp: float = field(default_factory=time.time)

    @property
    def hallucination_rate(self) -> float:
        if self.evidence_total == 0:
            return 0.0
        return round(1 - self.evidence_verified / self.evidence_total, 3)

    @property
    def scrape_failure_rate(self) -> float:
        total = self.pages_scraped + self.pages_failed
        return round(self.pages_failed / total, 3) if total else 0.0


class MetricsStore:
    """In-memory ring buffer of per-query metrics."""

    def __init__(self, maxlen: int = 200) -> None:
        self._records: deque[QueryMetrics] = deque(maxlen=maxlen)

    def record(self, m: QueryMetrics) -> None:
        self._records.append(m)

    def summary(self) -> dict:
        records = list(self._records)
        if not records:
            return {"total_queries": 0}

        n = len(records)
        return {
            "total_queries": n,
            "avg_latency_s": round(sum(r.total_time for r in records) / n, 2),
            "avg_entities_returned": round(sum(r.entities_final for r in records) / n, 1),
            "avg_hallucination_rate": round(sum(r.hallucination_rate for r in records) / n, 3),
            "avg_scrape_failure_rate": round(sum(r.scrape_failure_rate for r in records) / n, 3),
            "total_estimated_cost_usd": round(sum(r.estimated_cost_usd for r in records), 4),
            "avg_cost_per_query_usd": round(sum(r.estimated_cost_usd for r in records) / n, 4),
            "avg_stage_timings": {
                stage: round(
                    sum(r.stage_timings.get(stage, 0) for r in records) / n, 2
                )
                for stage in ("search", "scrape", "extract", "aggregate")
            },
            "recent": [
                {
                    "query": r.query,
                    "entity_type": r.entity_type,
                    "entities": r.entities_final,
                    "hallucination_rate": r.hallucination_rate,
                    "cost_usd": r.estimated_cost_usd,
                    "time_s": round(r.total_time, 2),
                }
                for r in list(records)[-10:]
            ],
        }


# Singleton — imported by orchestrator and routes
metrics_store = MetricsStore()
