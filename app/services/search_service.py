from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List

import requests
from openai import OpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.models.entity_models import SearchResult

logger = get_logger(__name__)

# Low-trust domains — deprioritised when merging results
_LOW_TRUST_DOMAINS = {"reddit.com", "quora.com", "twitter.com", "x.com", "facebook.com"}


class SearchService:
    def __init__(self) -> None:
        self.provider = settings.search_provider.lower().strip()
        self.api_key = settings.search_api_key
        self.timeout = settings.request_timeout_seconds
        self.max_results = settings.max_search_results
        self._llm = OpenAI(api_key=settings.openai_api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[SearchResult]:
        """Single-query search (used by debug endpoints)."""
        return self._search_serpapi(query.strip()) if query.strip() else []

    def search_multi(self, query: str) -> List[SearchResult]:
        """
        Multi-query retrieval:
          1. Generate up to 2 LLM query variants alongside the original.
          2. Run all queries in parallel against SerpAPI.
          3. Merge results, deduplicate by URL, deprioritise low-trust domains.
        """
        variants = self._generate_query_variants(query)
        logger.info("query_variants query=%r variants=%r", query, variants)

        seen_urls: set[str] = set()
        high_trust: List[SearchResult] = []
        low_trust: List[SearchResult] = []
        rank_counter = 1

        with ThreadPoolExecutor(max_workers=len(variants)) as pool:
            futures = {pool.submit(self._search_serpapi, v): v for v in variants}
            for future in as_completed(futures):
                for result in future.result():
                    if result.url in seen_urls:
                        continue
                    seen_urls.add(result.url)
                    result = result.model_copy(update={"rank": rank_counter})
                    rank_counter += 1
                    domain = result.url.split("/")[2] if "//" in result.url else ""
                    if any(d in domain for d in _LOW_TRUST_DOMAINS):
                        low_trust.append(result)
                    else:
                        high_trust.append(result)

        merged = high_trust + low_trust
        logger.info(
            "search_multi query=%r variants=%d total_results=%d",
            query, len(variants), len(merged),
        )
        return merged

    # ------------------------------------------------------------------
    # Query expansion
    # ------------------------------------------------------------------

    def _generate_query_variants(self, query: str) -> List[str]:
        """Use GPT-4o-mini to produce up to 2 alternative search queries."""
        try:
            response = self._llm.chat.completions.create(
                model=settings.openai_model,
                temperature=0.3,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate search query variants to improve web search coverage. "
                            "Return ONLY a valid JSON array of exactly 3 query strings. "
                            "Include the original query as the first element. "
                            "Make the other two distinct in phrasing or angle. "
                            "No explanation, no markdown, just the JSON array."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f'Original query: "{query}"',
                    },
                ],
            )
            raw = response.choices[0].message.content or "[]"
            variants: List[str] = json.loads(raw)
            if not isinstance(variants, list):
                return [query]
            # Always include original, take up to 3 total
            cleaned = [str(v).strip() for v in variants if str(v).strip()]
            if query not in cleaned:
                cleaned.insert(0, query)
            return cleaned[:3]
        except Exception as exc:
            logger.warning("query_expansion_failed query=%r error=%s", query, exc)
            return [query]

    # ------------------------------------------------------------------
    # SerpAPI
    # ------------------------------------------------------------------

    def _search_serpapi(self, query: str) -> List[SearchResult]:
        if not self.api_key:
            logger.warning("search_api_key not set — skipping search")
            return []

        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": self.api_key,
                    "num": self.max_results,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.error("serpapi_error query=%r error=%s", query, exc)
            return []

        return self._parse_serpapi_results(payload)

    def _parse_serpapi_results(self, payload: dict[str, Any]) -> List[SearchResult]:
        results: List[SearchResult] = []
        for i, item in enumerate(payload.get("organic_results", []), start=1):
            title = (item.get("title") or "").strip()
            url = (item.get("link") or "").strip()
            if not title or not url:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=(item.get("snippet") or "").strip() or None,
                    rank=i,
                )
            )
        return results
