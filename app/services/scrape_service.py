from __future__ import annotations

from typing import List, Optional

import requests
import trafilatura

from app.core.config import settings
from app.models.entity_models import ScrapedDocument, SearchResult


class ScrapeService:
    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.max_text_chars = 15000

    def scrape_search_results(self, search_results: List[SearchResult]) -> List[ScrapedDocument]:
        scraped_documents: List[ScrapedDocument] = []

        for result in search_results:
            document = self.scrape_url(
                url=result.url,
                source_rank=result.rank,
                fallback_title=result.title,
            )
            scraped_documents.append(document)

        return scraped_documents

    def scrape_url(
        self,
        url: str,
        source_rank: int,
        fallback_title: Optional[str] = None,
    ) -> ScrapedDocument:
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            )
            response.raise_for_status()
            html = response.text
        except requests.RequestException:
            return ScrapedDocument(
                url=url,
                title=fallback_title,
                text=None,
                source_rank=source_rank,
                fetch_success=False,
            )

        extracted_text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )

        if extracted_text:
            cleaned_text = extracted_text.strip()
            if len(cleaned_text) > self.max_text_chars:
                cleaned_text = cleaned_text[: self.max_text_chars]
        else:
            cleaned_text = None

        return ScrapedDocument(
            url=url,
            title=fallback_title,
            text=cleaned_text,
            source_rank=source_rank,
            fetch_success=cleaned_text is not None,
        )