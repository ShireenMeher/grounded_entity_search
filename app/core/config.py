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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
print("API KEY LOADED:", bool(settings.openai_api_key))