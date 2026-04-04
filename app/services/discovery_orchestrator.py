from app.services.query_service import QueryService
from app.services.search_service import SearchService
from app.services.scrape_service import ScrapeService
from app.services.extraction_service import ExtractionService
from app.services.aggregation_service import AggregationService

class DiscoveryOrchestrator:
    def __init__(self) -> None:
        self.query_service = QueryService()
        self.search_service = SearchService()
        self.scrape_service = ScrapeService()
        self.extraction_service = ExtractionService()
        self.aggregation_service = AggregationService()

    def run(self, query: str):
        interpretation = self.query_service.interpret_query(query)
        search_results = self.search_service.search(query)
        scraped_documents = self.scrape_service.scrape_search_results(search_results)

        filtered_docs = [
            d for d in scraped_documents
            if self._is_relevant_page(d, interpretation.entity_type)
        ]

        filtered_docs = filtered_docs[:3]

        all_entities = []
        for document in filtered_docs:
            entities = self.extraction_service.extract_entities_from_document(
                query=query,
                entity_type=interpretation.entity_type,
                schema_fields=interpretation.schema_fields,
                document=document,
            )
            all_entities.extend(entities)

        source_ranks = {doc.url: doc.source_rank for doc in scraped_documents}
        final_entities = self.aggregation_service.aggregate(all_entities, source_ranks, query, interpretation.entity_type,)
        metadata = {
            "search_results_considered": len(search_results),
            "pages_scraped": sum(1 for d in scraped_documents if d.fetch_success),
            "entities_extracted_before_dedup": len(all_entities),
            "entities_after_dedup": len(final_entities),
        }

        return interpretation, final_entities, metadata
    
    def _is_relevant_page(self, doc, entity_type: str):
        text = (doc.text or "").lower()

        KEYWORDS = {
            "software_tool": ["database", "sql", "tool", "open source", "client"],
            "restaurant": ["restaurant", "food", "menu", "cuisine", "dining"],
            "company": ["company", "startup", "business", "founded", "industry"],
            "generic_entity": []
        }

        keywords = KEYWORDS.get(entity_type, [])

        if not keywords:
            return True

        return any(k in text for k in keywords)