from app.services.extraction_service import ExtractionService


class TestParseJsonResponse:
    def setup_method(self):
        self.service = ExtractionService()

    def test_parses_raw_json(self):
        result = self.service._parse_json_response('{"entities": []}')
        assert result == {"entities": []}

    def test_parses_json_wrapped_in_markdown_fence(self):
        raw = '```json\n{"entities": [{"name": {"value": "X", "evidence": "Y"}}]}\n```'
        result = self.service._parse_json_response(raw)
        assert result["entities"][0]["name"]["value"] == "X"

    def test_parses_json_embedded_in_surrounding_text(self):
        raw = 'Here is the result: {"entities": []} — hope that helps!'
        result = self.service._parse_json_response(raw)
        assert result == {"entities": []}

    def test_returns_none_for_garbage(self):
        assert self.service._parse_json_response("not json at all") is None

    def test_returns_none_for_empty_string(self):
        assert self.service._parse_json_response("   ") is None


class TestCleanValue:
    def setup_method(self):
        self.service = ExtractionService()

    def test_normalises_open_source_synonyms(self):
        assert self.service._clean_value("open_source_status", "Open Source") == "open_source"
        assert self.service._clean_value("open_source_status", "opensource") == "open_source"
        assert self.service._clean_value("open_source_status", "yes") == "open_source"

    def test_normalises_closed_source_synonyms(self):
        assert self.service._clean_value("open_source_status", "Closed Source") == "not_open_source"
        assert self.service._clean_value("open_source_status", "no") == "not_open_source"

    def test_unrecognised_open_source_value_is_dropped(self):
        assert self.service._clean_value("open_source_status", "sort of") is None

    def test_literal_null_string_becomes_none(self):
        assert self.service._clean_value("description", "null") is None

    def test_passes_through_normal_string(self):
        assert self.service._clean_value("description", "  A great tool  ") == "A great tool"


class TestCleanEvidence:
    def setup_method(self):
        self.service = ExtractionService()

    def test_drops_document_url_reference(self):
        assert self.service._clean_evidence("Document URL: https://x.com") is None

    def test_drops_document_title_reference(self):
        assert self.service._clean_evidence("Document title: Some Page") is None

    def test_keeps_real_evidence(self):
        assert self.service._clean_evidence("Founded in 2019 by two engineers") == "Founded in 2019 by two engineers"


class TestVerifyEvidence:
    def setup_method(self):
        self.service = ExtractionService()

    def test_verified_when_substring_present(self):
        doc = "Joe's Pizza is a classic slice shop in Greenwich Village."
        evidence, verified = self.service._verify_evidence("classic slice shop", doc)
        assert verified is True

    def test_verified_is_case_and_whitespace_insensitive(self):
        doc = "Joe's   Pizza is a classic slice shop."
        evidence, verified = self.service._verify_evidence("PIZZA is a classic", doc)
        assert verified is True

    def test_unverified_when_not_present(self):
        doc = "Joe's Pizza is a classic slice shop."
        evidence, verified = self.service._verify_evidence("world famous since 1975", doc)
        assert verified is False

    def test_none_evidence_is_unverified(self):
        evidence, verified = self.service._verify_evidence(None, "any document text")
        assert verified is False
        assert evidence is None


class TestBuildEntityId:
    def setup_method(self):
        self.service = ExtractionService()

    def test_slugifies_name(self):
        assert self.service._build_entity_id("Joe's Pizza", "restaurant") == "joe-s-pizza"

    def test_strips_edition_phrases_for_software_tools(self):
        entity_id = self.service._build_entity_id("Metabase Community Edition", "software_tool")
        assert "community" not in entity_id
        assert "edition" not in entity_id

    def test_empty_name_falls_back(self):
        assert self.service._build_entity_id("   ", "restaurant") == "unknown-entity"


class TestIsMeaningfulEntity:
    def setup_method(self):
        self.service = ExtractionService()

    def _fields(self, name, **extra):
        from app.models.entity_models import ExtractedCell
        fields = {"name": ExtractedCell(value=name, source_url="https://x.com" if name else None)}
        for key, value in extra.items():
            fields[key] = ExtractedCell(value=value, source_url="https://x.com" if value else None)
        return fields

    def test_rejects_missing_name(self):
        fields = self._fields(None, cuisine="Pizza", neighborhood="SoHo")
        assert self.service._is_meaningful_entity(fields) is False

    def test_rejects_overly_long_name(self):
        long_name = "This Is Definitely Not A Real Proper Name"
        fields = self._fields(long_name, cuisine="Pizza", neighborhood="SoHo")
        assert self.service._is_meaningful_entity(fields) is False

    def test_rejects_insufficient_filled_fields(self):
        fields = self._fields("Joe's Pizza", cuisine="Pizza")
        assert self.service._is_meaningful_entity(fields) is False

    def test_accepts_valid_entity(self):
        fields = self._fields("Joe's Pizza", cuisine="Pizza", neighborhood="SoHo")
        assert self.service._is_meaningful_entity(fields) is True
