from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Optional

from app.core.config import settings


class QueryCache:
    """
    Small in-process TTL cache keyed by normalised query text.

    Scoped to a single instance/process — same trade-off as MetricsStore's
    in-memory ring buffer. Good enough for one Render dyno; would need a
    shared store (Redis) to work across multiple workers.
    """

    def __init__(self, max_entries: int = 200, ttl_seconds: int = 3600) -> None:
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def normalize_key(query: str) -> str:
        return " ".join(query.strip().lower().split())

    def get(self, query: str) -> Optional[Any]:
        key = self.normalize_key(query)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            timestamp, value = entry
            if time.time() - timestamp > self._ttl_seconds:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, query: str, value: Any) -> None:
        key = self.normalize_key(query)
        with self._lock:
            self._store[key] = (time.time(), value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


query_cache = QueryCache(ttl_seconds=settings.query_cache_ttl_seconds)
