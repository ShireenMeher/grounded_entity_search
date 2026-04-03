from dataclasses import dataclass


SCHEMA_TEMPLATES = {
    "company": [
        "name",
        "website",
        "description",
        "category",
        "location",
    ],
    "restaurant": [
        "name",
        "neighborhood",
        "cuisine",
        "notable_feature",
        "website_or_listing",
    ],
    "software_tool": [
        "name",
        "website_or_repo",
        "description",
        "open_source_status",
        "primary_use_case",
    ],
    "generic_entity": [
        "name",
        "description",
        "source",
    ],
}


@dataclass
class QueryInterpretation:
    entity_type: str
    schema_fields: list[str]


class QueryService:
    def interpret_query(self, query: str) -> QueryInterpretation:
        normalized_query = query.strip().lower()

        entity_type = self._infer_entity_type(normalized_query)
        schema_fields = SCHEMA_TEMPLATES[entity_type]

        return QueryInterpretation(
            entity_type=entity_type,
            schema_fields=schema_fields,
        )

    def _infer_entity_type(self, query: str) -> str:
        restaurant_keywords = [
            "restaurant",
            "restaurants",
            "pizza",
            "cafe",
            "cafes",
            "coffee shop",
            "coffee shops",
            "bakery",
            "bakeries",
            "bar",
            "bars",
            "places to eat",
            "food places",
        ]

        company_keywords = [
            "startup",
            "startups",
            "company",
            "companies",
            "business",
            "businesses",
            "firm",
            "firms",
            "healthtech",
            "fintech",
            "ai company",
            "ai companies",
        ]

        software_keywords = [
            "software",
            "tool",
            "tools",
            "platform",
            "platforms",
            "open source",
            "opensource",
            "database",
            "databases",
            "framework",
            "frameworks",
            "library",
            "libraries",
            "repo",
            "repositories",
            "github",
        ]

        if any(keyword in query for keyword in restaurant_keywords):
            return "restaurant"

        if any(keyword in query for keyword in company_keywords):
            return "company"

        if any(keyword in query for keyword in software_keywords):
            return "software_tool"

        return "generic_entity"