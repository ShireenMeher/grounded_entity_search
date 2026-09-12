from unittest.mock import patch

from app.models.entity_models import SearchResult
from app.services.search_service import SearchService


class TestParseSerpapiResults:
    def setup_method(self):
        self.service = SearchService()

    def test_parses_organic_results(self):
        payload = {
            "organic_results": [
                {"title": "Joe's Pizza", "link": "https://joespizza.com", "snippet": "Classic NY slice"},
                {"title": "Prince St. Pizza", "link": "https://princestpizza.com", "snippet": "Square slices"},
            ]
        }
        results = self.service._parse_serpapi_results(payload)
        assert len(results) == 2
        assert results[0].title == "Joe's Pizza"
        assert results[0].url == "https://joespizza.com"
        assert results[0].rank == 1
        assert results[1].rank == 2

    def test_skips_results_missing_title_or_link(self):
        payload = {
            "organic_results": [
                {"title": "", "link": "https://a.com", "snippet": "no title"},
                {"title": "No Link", "link": "", "snippet": "no link"},
                {"title": "Valid", "link": "https://b.com", "snippet": "fine"},
            ]
        }
        results = self.service._parse_serpapi_results(payload)
        assert len(results) == 1
        assert results[0].title == "Valid"

    def test_missing_snippet_becomes_none(self):
        payload = {"organic_results": [{"title": "X", "link": "https://x.com"}]}
        results = self.service._parse_serpapi_results(payload)
        assert results[0].snippet is None

    def test_empty_payload_returns_empty_list(self):
        assert self.service._parse_serpapi_results({}) == []


class TestSearchMultiFallback:
    def setup_method(self):
        self.service = SearchService()

    def test_retries_with_longer_timeout_when_all_variants_fail(self):
        fallback_result = [SearchResult(title="Found it", url="https://a.com", snippet=None, rank=1)]

        with patch.object(
            self.service, "_generate_query_variants", return_value=["only query"],
        ), patch.object(
            self.service, "_search_serpapi", side_effect=[[], fallback_result],
        ) as mock_search:
            results = self.service.search_multi("only query")

        assert results == fallback_result
        # first call is the normal per-variant search, second is the
        # longer-timeout fallback after everything came back empty
        assert mock_search.call_count == 2
        _, fallback_kwargs = mock_search.call_args_list[1]
        assert fallback_kwargs["timeout"] == self.service.timeout * 3

    def test_no_retry_needed_when_a_variant_succeeds(self):
        result = [SearchResult(title="Found it", url="https://a.com", snippet=None, rank=1)]

        with patch.object(
            self.service, "_generate_query_variants", return_value=["only query"],
        ), patch.object(
            self.service, "_search_serpapi", return_value=result,
        ) as mock_search:
            results = self.service.search_multi("only query")

        assert len(results) == 1
        assert mock_search.call_count == 1
