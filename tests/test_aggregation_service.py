from app.models.entity_models import ExtractedCell, ExtractedEntity
from app.services.aggregation_service import AggregationService, _dedup_key


def _cell(value, source_url="https://example.com", evidence=None):
    return ExtractedCell(value=value, source_url=source_url if value is not None else None, evidence=evidence)


def _entity(entity_id, name, fields=None, sources=None):
    fields = fields or {}
    fields.setdefault("name", _cell(name))
    return ExtractedEntity(
        entity_id=entity_id,
        entity_type="restaurant",
        fields=fields,
        supporting_sources=sources or ["https://example.com"],
        score=0.0,
    )


class TestDedupKey:
    def test_strips_trailing_type_suffix(self):
        assert _dedup_key("chrissys-pizza") == "chrissys"
        assert _dedup_key("dominos-pizzeria") == "dominos"
        assert _dedup_key("joes-eatery") == "joes"

    def test_leaves_unmatched_id_unchanged(self):
        assert _dedup_key("chrissys") == "chrissys"

    def test_never_returns_empty_string(self):
        # a name that is entirely a suffix word should fall back to itself
        assert _dedup_key("pizza") == "pizza"


class TestAggregate:
    def test_merges_entities_with_same_dedup_key(self):
        service = AggregationService()
        e1 = _entity(
            "chrissys-pizza", "Chrissy's Pizza",
            fields={"cuisine": _cell("Italian", evidence="Italian-style pies")},
            sources=["https://a.com"],
        )
        e2 = _entity(
            "chrissys", "Chrissy's",
            fields={"cuisine": _cell("Pizza", evidence="short")},
            sources=["https://b.com"],
        )

        merged = service.aggregate([e1, e2], source_ranks={}, query="pizza", entity_type="restaurant")

        assert len(merged) == 1
        assert set(merged[0].supporting_sources) == {"https://a.com", "https://b.com"}

    def test_keeps_distinct_entities_separate(self):
        service = AggregationService()
        e1 = _entity("joes-pizza", "Joe's Pizza")
        e2 = _entity("chrissys-pizza", "Chrissy's Pizza")

        merged = service.aggregate([e1, e2], source_ranks={}, query="pizza", entity_type="restaurant")

        assert {e.entity_id for e in merged} == {"joes-pizza", "chrissys-pizza"}

    def test_prefers_cell_with_longer_evidence_on_conflict(self):
        service = AggregationService()
        e1 = _entity(
            "joes-pizza", "Joe's Pizza",
            fields={"cuisine": _cell("Pizza", evidence="short")},
        )
        e2 = _entity(
            "joes-pizza", "Joe's Pizza",
            fields={"cuisine": _cell("Neapolitan Pizza", evidence="a much longer and more descriptive snippet")},
        )

        merged = service.aggregate([e1, e2], source_ranks={}, query="pizza", entity_type="restaurant")

        assert merged[0].fields["cuisine"].value == "Neapolitan Pizza"

    def test_results_sorted_by_score_descending(self):
        service = AggregationService()
        rich = _entity(
            "joes-pizza", "Joe's Pizza",
            fields={
                "cuisine": _cell("Pizza", evidence="Joe's Pizza is a classic New York slice shop"),
                "neighborhood": _cell("Greenwich Village", evidence="located in Greenwich Village"),
            },
            sources=["https://a.com", "https://b.com"],
        )
        sparse = _entity("sparse-spot", "Sparse Spot", sources=["https://c.com"])

        merged = service.aggregate([sparse, rich], source_ranks={}, query="pizza", entity_type="restaurant")

        assert [e.entity_id for e in merged] == ["joes-pizza", "sparse-spot"]
        assert merged[0].score > merged[1].score


class TestScoringHelpers:
    def test_single_source_penalty_applies_without_official_site(self):
        service = AggregationService()
        entity = _entity("joes-pizza", "Joe's Pizza", sources=["https://a.com"])
        assert service._single_source_penalty(entity) == -1.0

    def test_single_source_penalty_waived_for_official_site(self):
        service = AggregationService()
        entity = _entity(
            "joespizza", "JoesPizza",
            fields={"website": _cell("https://joespizza.com")},
            sources=["https://joespizza.com"],
        )
        assert service._single_source_penalty(entity) == 0.0

    def test_is_official_site_matches_name_in_domain(self):
        service = AggregationService()
        entity = _entity(
            "joespizza", "JoesPizza",
            fields={"website": _cell("https://joespizza.com")},
        )
        assert service._is_official_site(entity) is True

    def test_is_official_site_false_when_no_website(self):
        service = AggregationService()
        entity = _entity("joes-pizza", "Joe's Pizza")
        assert service._is_official_site(entity) is False

    def test_evidence_quality_zero_without_evidence(self):
        service = AggregationService()
        entity = _entity("joes-pizza", "Joe's Pizza", fields={"cuisine": _cell("Pizza")})
        assert service._evidence_quality_score(entity) == 0.0

    def test_evidence_quality_positive_with_evidence(self):
        service = AggregationService()
        entity = _entity(
            "joes-pizza", "Joe's Pizza",
            fields={"cuisine": _cell("Pizza", evidence="a reasonably long and specific piece of evidence text")},
        )
        assert service._evidence_quality_score(entity) > 0.0
