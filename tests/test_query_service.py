from app.services.query_service import QueryService


class TestParseClassification:
    def setup_method(self):
        self.service = QueryService()

    def test_parses_well_formed_response(self):
        raw = '{"entity_type": "restaurant", "schema_fields": ["name", "cuisine", "neighborhood"]}'
        result = self.service._parse_classification(raw)
        assert result.entity_type == "restaurant"
        assert result.schema_fields == ["name", "cuisine", "neighborhood"]

    def test_strips_markdown_fences(self):
        raw = '```json\n{"entity_type": "company", "schema_fields": ["name", "website"]}\n```'
        result = self.service._parse_classification(raw)
        assert result.entity_type == "company"

    def test_rejects_invalid_entity_type(self):
        raw = '{"entity_type": "banana", "schema_fields": ["name"]}'
        assert self.service._parse_classification(raw) is None

    def test_rejects_malformed_json(self):
        assert self.service._parse_classification("not json") is None

    def test_rejects_missing_schema_fields(self):
        raw = '{"entity_type": "restaurant", "schema_fields": []}'
        assert self.service._parse_classification(raw) is None

    def test_inserts_name_first_when_missing(self):
        raw = '{"entity_type": "restaurant", "schema_fields": ["cuisine", "neighborhood"]}'
        result = self.service._parse_classification(raw)
        assert result.schema_fields[0] == "name"

    def test_moves_name_to_front_when_present_but_not_first(self):
        raw = '{"entity_type": "restaurant", "schema_fields": ["cuisine", "name", "neighborhood"]}'
        result = self.service._parse_classification(raw)
        assert result.schema_fields[0] == "name"
        assert result.schema_fields.count("name") == 1

    def test_caps_at_six_fields(self):
        raw = '{"entity_type": "restaurant", "schema_fields": ["name", "a", "b", "c", "d", "e", "f", "g"]}'
        result = self.service._parse_classification(raw)
        assert len(result.schema_fields) == 6

    def test_sanitises_field_names_to_snake_case(self):
        raw = '{"entity_type": "company", "schema_fields": ["name", "Website URL"]}'
        result = self.service._parse_classification(raw)
        assert "website_url" in result.schema_fields


class TestKeywordFallback:
    def setup_method(self):
        self.service = QueryService()

    def test_matches_restaurant_keywords(self):
        result = self.service._keyword_fallback("best tacos in LA")
        assert result.entity_type == "restaurant"

    def test_matches_company_keywords(self):
        result = self.service._keyword_fallback("AI startups in healthcare")
        assert result.entity_type == "company"

    def test_matches_software_tool_keywords(self):
        result = self.service._keyword_fallback("open source database tools")
        assert result.entity_type == "software_tool"

    def test_falls_back_to_generic_entity(self):
        result = self.service._keyword_fallback("best sci-fi novels of 2024")
        assert result.entity_type == "generic_entity"

    def test_fallback_schema_always_starts_with_name(self):
        result = self.service._keyword_fallback("top pizza places")
        assert result.schema_fields[0] == "name"
