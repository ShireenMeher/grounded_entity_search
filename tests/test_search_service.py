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
