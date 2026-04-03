from typing import List, Dict
from pydantic import BaseModel, Field

from app.models.entity_models import ExtractedEntity


class DiscoverMetadata(BaseModel):
    search_results_considered: int = 0
    pages_scraped: int = 0
    entities_extracted_before_dedup: int = 0
    entities_after_dedup: int = 0


class DiscoverResponse(BaseModel):
    query: str
    entity_type: str
    schema_fields: List[str] = Field(default_factory=list)
    results: List[ExtractedEntity] = Field(default_factory=list)
    metadata: DiscoverMetadata