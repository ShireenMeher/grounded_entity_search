from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None
    rank: int


class ScrapedDocument(BaseModel):
    url: str
    title: Optional[str] = None
    text: Optional[str] = None
    source_rank: int
    fetch_success: bool = False


class ExtractedCell(BaseModel):
    value: Optional[str] = None
    source_url: Optional[str] = None
    evidence: Optional[str] = None


class ExtractedEntity(BaseModel):
    entity_id: str
    entity_type: str
    fields: Dict[str, ExtractedCell] = Field(default_factory=dict)
    supporting_sources: List[str] = Field(default_factory=list)
    score: float = 0.0