from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Grounded Entity Search"
    app_version: str = "0.1.0"

    openai_api_key: str = "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"
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