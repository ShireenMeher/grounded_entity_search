from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Fallback schema templates used when LLM classification fails
_FALLBACK_SCHEMAS: dict[str, list[str]] = {
    "company": ["name", "website", "description", "category", "location"],
    "restaurant": ["name", "neighborhood", "cuisine", "notable_feature", "website_or_listing"],
    "software_tool": ["name", "website_or_repo", "description", "open_source_status", "primary_use_case"],
    "generic_entity": ["name", "description", "category", "url"],
}

_VALID_ENTITY_TYPES = set(_FALLBACK_SCHEMAS.keys())

_SYSTEM_PROMPT = """\
You are a query classifier for a web entity search system.

Given a user query, determine:
1. The entity_type being searched for.
2. The most useful schema_fields for extracting structured data about those entities from web pages.

Entity types:
- "restaurant"    — food/dining places
- "company"       — businesses, startups, firms, organisations
- "software_tool" — software, apps, libraries, frameworks, databases, APIs, CLIs
- "generic_entity" — anything else (people, events, concepts, etc.)

Schema rules:
- Always put "name" first.
- Use snake_case field names (e.g. website_or_repo, not websiteOrRepo).
- 4–6 fields total. Choose fields that commonly appear on web pages about this entity type.
- For software_tool, always include "open_source_status" if open-source status is relevant.

Examples:
- "top pizza places in Brooklyn"
  → {"entity_type":"restaurant","schema_fields":["name","neighborhood","cuisine","notable_feature","website_or_listing"]}
- "AI startups in healthcare"
  → {"entity_type":"company","schema_fields":["name","website","description","category","location"]}
- "open source database tools"
  → {"entity_type":"software_tool","schema_fields":["name","website_or_repo","description","open_source_status","primary_use_case"]}
- "best sci-fi novels of 2024"
  → {"entity_type":"generic_entity","schema_fields":["name","author","description","genre","year"]}
- "venture capital firms in NYC"
  → {"entity_type":"company","schema_fields":["name","website","focus_area","portfolio_size","location"]}

Return ONLY valid JSON with keys "entity_type" and "schema_fields". No explanation, no markdown.
"""


@dataclass
class QueryInterpretation:
    entity_type: str
    schema_fields: list[str]


class QueryService:
    def __init__(self) -> None:
        self._llm = OpenAI(api_key=settings.openai_api_key)

    def interpret_query(self, query: str) -> QueryInterpretation:
        result = self._classify_with_llm(query.strip())
        logger.info(
            "query_classified query=%r entity_type=%s fields=%s",
            query, result.entity_type, result.schema_fields,
        )
        return result

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    def _classify_with_llm(self, query: str) -> QueryInterpretation:
        try:
            response = self._llm.chat.completions.create(
                model=settings.openai_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f'Query: "{query}"'},
                ],
            )
            raw = response.choices[0].message.content or ""
            parsed = self._parse_classification(raw)
            if parsed:
                return parsed
        except Exception as exc:
            logger.warning("llm_classification_failed query=%r error=%s", query, exc)

        # Fallback to keyword matching
        logger.info("falling_back_to_keyword_classification query=%r", query)
        return self._keyword_fallback(query)

    def _parse_classification(self, raw: str) -> QueryInterpretation | None:
        """Parse and validate the LLM JSON response."""
        try:
            # Strip markdown fences if present
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return None

        entity_type = data.get("entity_type", "").strip()
        schema_fields = data.get("schema_fields", [])

        if entity_type not in _VALID_ENTITY_TYPES:
            logger.warning("invalid_entity_type_from_llm value=%r", entity_type)
            return None

        if not isinstance(schema_fields, list) or not schema_fields:
            return None

        # Sanitise field names: lowercase snake_case, drop empties
        clean_fields = [
            re.sub(r"[^a-z0-9_]", "_", str(f).strip().lower())
            for f in schema_fields
            if str(f).strip()
        ]

        # Ensure "name" is always first
        if "name" not in clean_fields:
            clean_fields.insert(0, "name")
        elif clean_fields[0] != "name":
            clean_fields.remove("name")
            clean_fields.insert(0, "name")

        # Cap at 6 fields
        clean_fields = clean_fields[:6]

        return QueryInterpretation(entity_type=entity_type, schema_fields=clean_fields)

    # ------------------------------------------------------------------
    # Keyword fallback
    # ------------------------------------------------------------------

    def _keyword_fallback(self, query: str) -> QueryInterpretation:
        normalized = query.lower()

        restaurant_kw = [
            "restaurant", "restaurants", "pizza", "taco", "tacos", "sushi",
            "ramen", "burger", "burgers", "cafe", "cafes", "coffee shop",
            "bakery", "bakeries", "bar", "bars", "places to eat", "food places",
            "brunch", "diner", "diners", "bistro", "eatery", "eateries",
            "bbq", "steakhouse", "seafood",
        ]
        company_kw = [
            "startup", "startups", "company", "companies", "business",
            "businesses", "firm", "firms", "venture", "ventures",
            "healthtech", "fintech", "edtech", "proptech", "climatetech",
            "ai company", "ai companies", "saas", "b2b",
        ]
        software_kw = [
            "software", "app", "apps", "application", "applications",
            "tool", "tools", "platform", "platforms", "open source", "opensource",
            "database", "databases", "framework", "frameworks", "library",
            "libraries", "repo", "repositories", "github", "plugin", "plugins",
            "extension", "cli", "sdk", "api",
        ]

        if any(kw in normalized for kw in restaurant_kw):
            entity_type = "restaurant"
        elif any(kw in normalized for kw in company_kw):
            entity_type = "company"
        elif any(kw in normalized for kw in software_kw):
            entity_type = "software_tool"
        else:
            entity_type = "generic_entity"

        return QueryInterpretation(
            entity_type=entity_type,
            schema_fields=_FALLBACK_SCHEMAS[entity_type],
        )
