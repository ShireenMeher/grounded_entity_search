import os
from pydantic_settings import BaseSettings, SettingsConfigDict

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class Settings(BaseSettings):
    app_name: str = "Grounded Entity Search"
    app_version: str = "0.1.0"

    openai_api_key: str = OPENAI_API_KEY
    openai_model: str = "gpt-4o-mini"

    search_api_key: str = "6df5cfc43645e55308529be5d6984d6fe92e46af94145226db8f9fc5e91a7777"
    search_provider: str = "serpapi"

    max_search_results: int = 5
    request_timeout_seconds: int = 15

    # SerpAPI normally responds in under 1s (sequential calls; concurrent
    # calls on this plan get severely throttled — see search_service.py).
    # NOTE: this was previously set to 3s to shave latency, but that caused
    # a real outage in production — on Render's network, an occasional slow
    # SerpAPI response caused all 3 sequential variant calls to time out,
    # returning zero search results (and therefore zero entities) instead
    # of just a slower response. 6s trades a little latency for not
    # failing the whole query on a single slow leg.
    search_timeout_seconds: int = 6

    # Scraping is bounded separately: arbitrary third-party pages can hang,
    # and we only need the first few good ones for extraction.
    scrape_timeout_seconds: int = 8
    max_scrape_candidates: int = 8

    # How long a cached /discover result stays valid for a repeated query.
    query_cache_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
print("API KEY LOADED:", bool(settings.openai_api_key))