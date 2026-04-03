from fastapi import APIRouter

from app.models.request_models import DiscoverRequest
from app.models.response_models import DiscoverMetadata, DiscoverResponse
from app.services.query_service import QueryService
from app.services.search_service import SearchService
from app.services.scrape_service import ScrapeService
from app.services.extraction_service import ExtractionService

router = APIRouter()
query_service = QueryService()
search_service = SearchService()
scrape_service = ScrapeService()
extraction_service = ExtractionService()

@router.get("/")
def root() -> dict:
    return {"message": "Grounded Entity Search API is running"}


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.post("/discover", response_model=DiscoverResponse)
def discover_entities(payload: DiscoverRequest) -> DiscoverResponse:
    interpretation = query_service.interpret_query(payload.query)
    search_results = search_service.search(payload.query)

    return DiscoverResponse(
        query=payload.query,
        entity_type=interpretation.entity_type,
        schema_fields=interpretation.schema_fields,
        results=[],
        metadata=DiscoverMetadata(
            search_results_considered=len(search_results),
            pages_scraped=0,
            entities_extracted_before_dedup=0,
            entities_after_dedup=0,
        ),
    )

@router.post("/debug/search")
def debug_search(payload: DiscoverRequest) -> list[dict]:
    results = search_service.search(payload.query)
    return [result.model_dump() for result in results]

@router.post("/debug/scrape")
def debug_scrape(payload: DiscoverRequest) -> list[dict]:
    search_results = search_service.search(payload.query)
    scraped_documents = scrape_service.scrape_search_results(search_results)
    return [document.model_dump() for document in scraped_documents]

@router.post("/debug/extract")
def debug_extract(payload: DiscoverRequest) -> list[dict]:
    interpretation = query_service.interpret_query(payload.query)
    search_results = search_service.search(payload.query)
    scraped_documents = scrape_service.scrape_search_results(search_results)

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