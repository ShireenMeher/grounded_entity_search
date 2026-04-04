from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.logging import get_logger
from app.services.aggregation_service import AggregationService
from app.services.extraction_service import ExtractionService
from app.services.metrics_store import QueryMetrics, metrics_store
from app.services.query_service import QueryService
from app.services.scrape_service import ScrapeService
from app.services.search_service import SearchService

logger = get_logger(__name__)


class DiscoveryOrchestrator:
    def __init__(self) -> None:
        self.query_service = QueryService()
        self.search_service = SearchService()
        self.scrape_service = ScrapeService()
        self.extraction_service = ExtractionService()
        self.aggregation_service = AggregationService()

    def run(self, query: str):
        wall_start = time.perf_counter()
        stage_timings: dict[str, float] = {}

        # ── 1. Interpret query ─────────────────────────────────────────
        interpretation = self.query_service.interpret_query(query)
        logger.info(
            "query_interpreted query=%r entity_type=%s fields=%s",
            query, interpretation.entity_type, interpretation.schema_fields,
        )

        # ── 2. Multi-query retrieval ───────────────────────────────────
        t0 = time.perf_counter()
        search_results = self.search_service.search_multi(query)
        stage_timings["search"] = round(time.perf_counter() - t0, 2)
        logger.info("search_done results=%d time=%.2fs", len(search_results), stage_timings["search"])

        # ── 3. Pre-rank by snippet relevance ──────────────────────────
        search_results = self._rank_by_snippet_relevance(
            search_results, query, interpretation.entity_type
        )
        logger.info("snippet_reranked top_url=%s", search_results[0].url if search_results else "none")

        # ── 4. Scrape ──────────────────────────────────────────────────
        t0 = time.perf_counter()
        scraped_documents = self.scrape_service.scrape_search_results(search_results)
        stage_timings["scrape"] = round(time.perf_counter() - t0, 2)

        successful = [d for d in scraped_documents if d.fetch_success]
        failed_count = len(scraped_documents) - len(successful)
        logger.info(
            "scrape_done total=%d success=%d failed=%d time=%.2fs",
            len(scraped_documents), len(successful), failed_count, stage_timings["scrape"],
        )

        # ── 4. Relevance filter → top 3 ───────────────────────────────
        filtered_docs = [
            d for d in successful
            if self._is_relevant_page(d, interpretation.entity_type)
        ][:3]
        logger.info("relevance_filter kept=%d", len(filtered_docs))

        # ── 5. Parallel extraction ─────────────────────────────────────
        self.extraction_service.reset_stats()
        t0 = time.perf_counter()
        all_entities = []
        with ThreadPoolExecutor(max_workers=len(filtered_docs) or 1) as executor:
            futures = [
                executor.submit(
                    self.extraction_service.extract_entities_from_document,
                    query=query,
                    entity_type=interpretation.entity_type,
                    schema_fields=interpretation.schema_fields,
                    document=doc,
                )
                for doc in filtered_docs
            ]
            for future in as_completed(futures):
                all_entities.extend(future.result())
        stage_timings["extract"] = round(time.perf_counter() - t0, 2)

        hallucination_rate = (
            round(1 - self.extraction_service.evidence_verified /
                  self.extraction_service.evidence_total, 3)
            if self.extraction_service.evidence_total > 0 else 0.0
        )
        logger.info(
            "extract_done entities=%d evidence_total=%d verified=%d hallucination_rate=%.3f "
            "tokens_in=%d tokens_out=%d cost_usd=%.5f time=%.2fs",
            len(all_entities),
            self.extraction_service.evidence_total,
            self.extraction_service.evidence_verified,
            hallucination_rate,
            self.extraction_service.input_tokens,
            self.extraction_service.output_tokens,
            self.extraction_service.estimated_cost_usd,
            stage_timings["extract"],
        )

        # ── 6. Aggregate / deduplicate / rank ─────────────────────────
        t0 = time.perf_counter()
        source_ranks = {doc.url: doc.source_rank for doc in scraped_documents}
        final_entities = self.aggregation_service.aggregate(
            all_entities, source_ranks, query, interpretation.entity_type,
        )
        stage_timings["aggregate"] = round(time.perf_counter() - t0, 2)
        logger.info(
            "aggregate_done before=%d after=%d time=%.2fs",
            len(all_entities), len(final_entities), stage_timings["aggregate"],
        )

        total_time = round(time.perf_counter() - wall_start, 2)

        # ── 7. Record metrics ──────────────────────────────────────────
        metrics_store.record(
            QueryMetrics(
                query=query,
                entity_type=interpretation.entity_type,
                stage_timings=stage_timings,
                search_results_count=len(search_results),
                pages_scraped=len(successful),
                pages_failed=failed_count,
                entities_raw=len(all_entities),
                entities_final=len(final_entities),
                evidence_total=self.extraction_service.evidence_total,
                evidence_verified=self.extraction_service.evidence_verified,
                input_tokens=self.extraction_service.input_tokens,
                output_tokens=self.extraction_service.output_tokens,
                estimated_cost_usd=self.extraction_service.estimated_cost_usd,
                total_time=total_time,
            )
        )
        logger.info("pipeline_done query=%r total_time=%.2fs", query, total_time)

        metadata = {
            "search_results_considered": len(search_results),
            "pages_scraped": len(successful),
            "pages_failed": failed_count,
            "entities_extracted_before_dedup": len(all_entities),
            "entities_after_dedup": len(final_entities),
            "hallucination_rate": hallucination_rate,
            "evidence_verified": self.extraction_service.evidence_verified,
            "evidence_total": self.extraction_service.evidence_total,
            "estimated_cost_usd": self.extraction_service.estimated_cost_usd,
            "stage_timings": stage_timings,
        }
        return interpretation, final_entities, metadata

    # ------------------------------------------------------------------

    def _rank_by_snippet_relevance(
        self, results: list, query: str, entity_type: str
    ) -> list:
        """
        Re-order search results before scraping using a lightweight signal:
          - Query term overlap in title + snippet
          - Snippet length bonus (longer = more informative)
          - Domain trust penalty for low-quality sources
          - Entity-type keyword bonus in snippet

        No LLM call — pure string scoring, runs in <1ms.
        """
        _STOP_WORDS = {
            "in", "the", "a", "an", "of", "for", "to", "and", "or",
            "with", "at", "by", "on", "is", "are", "was", "were",
        }
        _LOW_TRUST = {"reddit.com", "quora.com", "twitter.com", "x.com", "pinterest.com"}
        _TYPE_KEYWORDS: dict[str, list[str]] = {
            "restaurant": ["restaurant", "food", "menu", "dining", "eat", "taco", "pizza"],
            "company": ["startup", "company", "business", "founded", "funding", "team"],
            "software_tool": ["open source", "github", "library", "framework", "tool", "api"],
            "generic_entity": [],
        }

        query_terms = {
            t for t in query.lower().split() if t not in _STOP_WORDS and len(t) > 2
        }
        type_kws = _TYPE_KEYWORDS.get(entity_type, [])

        def _score(result) -> float:
            text = (
                (result.title or "") + " " + (result.snippet or "")
            ).lower()

            # Query term overlap (primary signal)
            term_score = sum(2.0 for t in query_terms if t in text)

            # Entity-type keyword bonus
            type_score = sum(1.0 for kw in type_kws if kw in text)

            # Snippet length bonus — longer snippets are richer
            snippet_len = len(result.snippet or "")
            length_bonus = min(snippet_len / 150.0, 1.5)

            # Domain trust penalty
            domain = result.url.split("/")[2] if "//" in result.url else ""
            trust_penalty = -3.0 if any(d in domain for d in _LOW_TRUST) else 0.0

            return term_score + type_score + length_bonus + trust_penalty

        reranked = sorted(results, key=_score, reverse=True)

        if results and reranked[0].url != results[0].url:
            logger.info(
                "snippet_rerank changed top result: %s → %s",
                results[0].url, reranked[0].url,
            )

        return reranked

    def _is_relevant_page(self, doc, entity_type: str) -> bool:
        text = (doc.text or "").lower()
        KEYWORDS = {
            "software_tool": ["software", "app", "tool", "open source", "platform", "framework", "database"],
            "restaurant": ["restaurant", "food", "menu", "cuisine", "dining", "taco", "pizza", "ramen", "burger", "eat"],
            "company": ["company", "startup", "business", "founded", "industry", "saas", "venture"],
            "generic_entity": [],
        }
        keywords = KEYWORDS.get(entity_type, [])
        return not keywords or any(k in text for k in keywords)
