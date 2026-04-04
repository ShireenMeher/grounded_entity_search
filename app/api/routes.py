from fastapi import APIRouter
import time

from app.models.request_models import DiscoverRequest
from app.services.query_service import QueryService
from app.services.search_service import SearchService
from app.services.scrape_service import ScrapeService
from app.services.extraction_service import ExtractionService
from app.services.discovery_orchestrator import DiscoveryOrchestrator
from app.services.metrics_store import metrics_store

router = APIRouter()
query_service = QueryService()
search_service = SearchService()
scrape_service = ScrapeService()
extraction_service = ExtractionService()
discovery_orchestrator = DiscoveryOrchestrator()

TOP_K_SCRAPE = 5
TOP_K_EXTRACT = 3



@router.get("/")
def root() -> dict:
    return {"message": "Grounded Entity Search API is running"}


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.post("/discover")
def discover_entities(payload: DiscoverRequest) -> dict:
    start = time.time()
    interpretation, entities, metadata = discovery_orchestrator.run(payload.query)
    elapsed = time.time() - start

    return {
        "query": payload.query,
        "entity_type": interpretation.entity_type,
        "schema_fields": interpretation.schema_fields,
        "results": [e.model_dump() for e in entities],
        "metadata": metadata,
        "execution_time_seconds": elapsed,
    }

@router.post("/debug/search")
def debug_search(payload: DiscoverRequest) -> list[dict]:
    results = search_service.search(payload.query)
    return [result.model_dump() for result in results]

@router.post("/debug/scrape")
def debug_scrape(payload: DiscoverRequest) -> list[dict]:
    search_results = search_service.search(payload.query)
    top_search_results = search_results[:TOP_K_SCRAPE]

    scraped_documents = scrape_service.scrape_search_results(top_search_results)

    # Only keep successful ones
    scraped_documents = [d for d in scraped_documents if d.fetch_success]

    # Only extract from top few pages
    scraped_documents = scraped_documents[:TOP_K_EXTRACT]
    return [document.model_dump() for document in scraped_documents]

@router.post("/debug/extract")
def debug_extract(payload: DiscoverRequest) -> list[dict]:
    interpretation = query_service.interpret_query(payload.query)
    search_results = search_service.search(payload.query)
    top_search_results = search_results[:TOP_K_SCRAPE]

    scraped_documents = scrape_service.scrape_search_results(top_search_results)

    # Only keep successful ones
    scraped_documents = [d for d in scraped_documents if d.fetch_success]

    # Only extract from top few pages
    scraped_documents = scraped_documents[:TOP_K_EXTRACT]

    all_entities = []

    for document in scraped_documents:
        extracted_entities = extraction_service.extract_entities_from_document(
            query=payload.query,
            entity_type=interpretation.entity_type,
            schema_fields=interpretation.schema_fields,
            document=document,
        )
        all_entities.extend(extracted_entities)

    return [entity.model_dump() for entity in all_entities]

@router.get("/metrics")
def get_metrics() -> dict:
    return metrics_store.summary()


@router.post("/debug/discover")
def debug_discover(payload: DiscoverRequest) -> dict:

    start = time.time()

    interpretation, entities, metadata = discovery_orchestrator.run(payload.query)

    end = time.time()
    return {
        "query": payload.query,
        "entity_type": interpretation.entity_type,
        "schema_fields": interpretation.schema_fields,
        "results": [e.model_dump() for e in entities],
        "metadata": metadata,
        "execution_time_seconds": end - start
    }