from __future__ import annotations

from typing import Any, List

import requests

from app.core.config import settings
from app.models.entity_models import SearchResult


class SearchService:
    def __init__(self) -> None:
        self.provider = settings.search_provider.lower().strip()
        self.api_key = settings.search_api_key
        self.timeout = settings.request_timeout_seconds
        self.max_results = settings.max_search_results

    def search(self, query: str) -> List[SearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        if self.provider == "serpapi":
            return self._search_serpapi(normalized_query)

        raise ValueError(f"Unsupported search provider: {self.provider}")

    def _search_serpapi(self, query: str) -> List[SearchResult]:
        if not self.api_key:
            return []

        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            "num": self.max_results,
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            return []
        except ValueError:
            return []

        return self._parse_serpapi_results(payload)

    def _parse_serpapi_results(self, payload: dict[str, Any]) -> List[SearchResult]:
        raw_results = payload.get("organic_results", [])

        normalized_results: List[SearchResult] = []

        for index, item in enumerate(raw_results, start=1):
            title = (item.get("title") or "").strip()
            url = (item.get("link") or "").strip()
            snippet = (item.get("snippet") or "").strip() or None

            if not title or not url:
                continue

            normalized_results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    rank=index,
                )
            )

        return normalized_results