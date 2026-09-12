from unittest.mock import patch

from app.models.entity_models import ExtractedCell, ExtractedEntity, ScrapedDocument, SearchResult
from app.services.discovery_orchestrator import DiscoveryOrchestrator
from app.services.query_cache import query_cache
from app.services.query_service import QueryInterpretation


def _search_result(url, rank, title="Title", snippet="snippet"):
    return SearchResult(title=title, url=url, snippet=snippet, rank=rank)


def _scraped_doc(url, rank, text="Joe's Pizza is a great spot for classic New York pizza.", success=True):
    return ScrapedDocument(url=url, title="Title", text=text, source_rank=rank, fetch_success=success)


def _entity(entity_id, name, url):
    return ExtractedEntity(
        entity_id=entity_id,
        entity_type="restaurant",
        fields={
            "name": ExtractedCell(value=name, source_url=url, evidence=name),
            "cuisine": ExtractedCell(value="Pizza", source_url=url, evidence="classic New York pizza"),
            "neighborhood": ExtractedCell(value="SoHo", source_url=url, evidence="in SoHo"),
        },
        supporting_sources=[url],
        score=0.0,
    )


_INTERPRETATION = QueryInterpretation(
    entity_type="restaurant", schema_fields=["name", "cuisine", "neighborhood"]
)


class TestDiscoveryOrchestratorRun:
    def setup_method(self):
        query_cache.clear()

    def teardown_method(self):
        query_cache.clear()

    def test_pipeline_composes_stages_into_final_output(self):
        orchestrator = DiscoveryOrchestrator()

        search_results = [_search_result("https://a.com", 1), _search_result("https://b.com", 2)]
        scraped = [_scraped_doc("https://a.com", 1), _scraped_doc("https://b.com", 2)]
        entities_a = [_entity("joes-pizza", "Joe's Pizza", "https://a.com")]
        entities_b = [_entity("joes-pizza", "Joe's Pizza", "https://b.com")]

        def fake_extract(query, entity_type, schema_fields, document):
            return entities_a if document.url == "https://a.com" else entities_b

        with patch.object(
            orchestrator.query_service, "interpret_query", return_value=_INTERPRETATION,
        ), patch.object(
            orchestrator.search_service, "search_multi", return_value=search_results,
        ), patch.object(
            orchestrator.scrape_service, "scrape_search_results", return_value=scraped,
        ), patch.object(
            orchestrator.extraction_service, "extract_entities_from_document", side_effect=fake_extract,
        ):
            interpretation, final_entities, metadata = orchestrator.run("best pizza in SoHo")

        assert interpretation.entity_type == "restaurant"
        # entities from both sources share a dedup key and should merge into one
        assert len(final_entities) == 1
        assert set(final_entities[0].supporting_sources) == {"https://a.com", "https://b.com"}
        assert metadata["pages_scraped"] == 2
        assert metadata["pages_failed"] == 0
        assert metadata["entities_extracted_before_dedup"] == 2
        assert metadata["entities_after_dedup"] == 1
        assert metadata["served_from_cache"] is False
        assert set(metadata["stage_timings"].keys()) == {"search", "scrape", "extract", "aggregate"}

    def test_pipeline_handles_no_relevant_pages(self):
        orchestrator = DiscoveryOrchestrator()

        search_results = [_search_result("https://a.com", 1, title="unrelated", snippet="nothing here")]
        scraped = [_scraped_doc("https://a.com", 1, text="Completely unrelated content about tax law.")]

        with patch.object(
            orchestrator.query_service, "interpret_query", return_value=_INTERPRETATION,
        ), patch.object(
            orchestrator.search_service, "search_multi", return_value=search_results,
        ), patch.object(
            orchestrator.scrape_service, "scrape_search_results", return_value=scraped,
        ), patch.object(
            orchestrator.extraction_service, "extract_entities_from_document", return_value=[],
        ):
            _, final_entities, metadata = orchestrator.run("obscure query with no matches")

        assert final_entities == []
        assert metadata["entities_after_dedup"] == 0


class TestDiscoveryOrchestratorCaching:
    def setup_method(self):
        query_cache.clear()

    def teardown_method(self):
        query_cache.clear()

    def test_repeated_query_is_served_from_cache_without_recomputation(self):
        orchestrator = DiscoveryOrchestrator()

        search_results = [_search_result("https://a.com", 1)]
        scraped = [_scraped_doc("https://a.com", 1)]
        entities = [_entity("joes-pizza", "Joe's Pizza", "https://a.com")]

        with patch.object(
            orchestrator.query_service, "interpret_query", return_value=_INTERPRETATION,
        ) as mock_interpret, patch.object(
            orchestrator.search_service, "search_multi", return_value=search_results,
        ) as mock_search, patch.object(
            orchestrator.scrape_service, "scrape_search_results", return_value=scraped,
        ) as mock_scrape, patch.object(
            orchestrator.extraction_service, "extract_entities_from_document", return_value=entities,
        ) as mock_extract:
            _, first_entities, first_metadata = orchestrator.run("cached pizza query")
            _, second_entities, second_metadata = orchestrator.run("cached pizza query")

        assert first_metadata["served_from_cache"] is False
        assert second_metadata["served_from_cache"] is True
        assert second_entities == first_entities
        assert mock_interpret.call_count == 1
        assert mock_search.call_count == 1
        assert mock_scrape.call_count == 1
        assert mock_extract.call_count == 1

    def test_cache_key_is_case_and_whitespace_insensitive(self):
        orchestrator = DiscoveryOrchestrator()

        search_results = [_search_result("https://a.com", 1)]
        scraped = [_scraped_doc("https://a.com", 1)]
        entities = [_entity("joes-pizza", "Joe's Pizza", "https://a.com")]

        with patch.object(
            orchestrator.query_service, "interpret_query", return_value=_INTERPRETATION,
        ), patch.object(
            orchestrator.search_service, "search_multi", return_value=search_results,
        ), patch.object(
            orchestrator.scrape_service, "scrape_search_results", return_value=scraped,
        ) as mock_scrape, patch.object(
            orchestrator.extraction_service, "extract_entities_from_document", return_value=entities,
        ):
            orchestrator.run("  Best Pizza In SoHo  ")
            _, _, metadata = orchestrator.run("best pizza in soho")

        assert metadata["served_from_cache"] is True
        assert mock_scrape.call_count == 1
