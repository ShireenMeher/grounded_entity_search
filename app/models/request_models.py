from pydantic import BaseModel, Field


class DiscoverRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Topic query to search and structure")