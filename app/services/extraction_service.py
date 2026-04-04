from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from openai import OpenAI

from app.core.config import settings
from app.models.entity_models import ExtractedCell, ExtractedEntity, ScrapedDocument
from app.prompts.extraction_prompts import (
    build_extraction_system_prompt,
    build_extraction_user_prompt,
)


class ExtractionService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def extract_entities_from_document(
        self,
        query: str,
        entity_type: str,
        schema_fields: List[str],
        document: ScrapedDocument,
    ) -> List[ExtractedEntity]:
        if not document.fetch_success or not document.text:
            return []

        system_prompt = build_extraction_system_prompt()
        user_prompt = build_extraction_user_prompt(
            query=query,
            entity_type=entity_type,
            schema_fields=schema_fields,
            document_url=document.url,
            document_title=document.title,
            document_text=document.text,
        )

        raw_content = self._call_llm(system_prompt, user_prompt)
        parsed_payload = self._parse_json_response(raw_content)

        if not parsed_payload:
            return []

        raw_entities = parsed_payload.get("entities", [])
        if not isinstance(raw_entities, list):
            return []

        extracted_entities: List[ExtractedEntity] = []
        print(f"[EXTRACT] url={document.url} parsed_entities={len(raw_entities) if isinstance(raw_entities, list) else 0}")

        for raw_entity in raw_entities:
            normalized_entity = self._normalize_entity(
                raw_entity=raw_entity,
                entity_type=entity_type,
                schema_fields=schema_fields,
                document_url=document.url,
            )
            if normalized_entity is not None:
                extracted_entities.append(normalized_entity)

        print(f"[EXTRACT] url={document.url} normalized_entities={len(extracted_entities)}")

        return extracted_entities

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = response.choices[0].message.content
        return content or ""

    def _parse_json_response(self, raw_content: str) -> Dict[str, Any] | None:
        if not raw_content.strip():
            return None

        try:
            return json.loads(raw_content)
        except json.JSONDecodeError:
            pass

        fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
        if fenced_match:
            try:
                return json.loads(fenced_match.group(1))
            except json.JSONDecodeError:
                return None

        first_brace = raw_content.find("{")
        last_brace = raw_content.rfind("}")
        if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
            candidate = raw_content[first_brace : last_brace + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None

        return None

    def _normalize_entity(
        self,
        raw_entity: Dict[str, Any],
        entity_type: str,
        schema_fields: List[str],
        document_url: str,
    ) -> ExtractedEntity | None:
        if not isinstance(raw_entity, dict):
            return None

        normalized_fields: Dict[str, ExtractedCell] = {}

        for field_name in schema_fields:
            raw_field = raw_entity.get(field_name)

            if isinstance(raw_field, dict):
                value = self._clean_value(field_name, raw_field.get("value"))
                evidence = self._clean_evidence(raw_field.get("evidence"))
            else:
                value = None
                evidence = None

            normalized_fields[field_name] = ExtractedCell(
                value=value,
                source_url=document_url if value is not None else None,
                evidence=evidence if value is not None else None,
            )

        if not self._is_meaningful_entity(normalized_fields):
            return None

        name_cell = normalized_fields["name"]

        entity_id = self._build_entity_id(name_cell.value)

        return ExtractedEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            fields=normalized_fields,
            supporting_sources=[document_url],
            score=0.0,
        )

    def _build_entity_id(self, name: str) -> str:
        normalized = name.strip().lower()

        # Remove noisy suffixes
        noise_words = [
            "community edition",
            "community",
            "ce",
            "open source edition",
            "edition",
        ]

        for word in noise_words:
            normalized = normalized.replace(word, "")

        normalized = normalized.strip()

        # Remove non-alphanumeric
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
        normalized = normalized.strip("-")
        return normalized or "unknown-entity"

    def _normalize_optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None

        cleaned = value.strip()
        return cleaned if cleaned else None
    
    def _clean_value(self, field_name: str, value: Any) -> str | None:
        normalized = self._normalize_optional_string(value)
        if normalized is None:
            return None

        if normalized.lower() == "null":
            return None

        if field_name == "open_source_status":
            lowered = normalized.strip().lower()

            if lowered in {
                "open source",
                "open-source",
                "free open-source",
                "free open source",
                "opensource",
                "open_source",
                "true",
                "yes",
            }:
                return "open_source"

            if lowered in {
                "not open source",
                "closed source",
                "closed-source",
                "false",
                "no",
            }:
                return "not_open_source"

            return None

        return normalized

    def _clean_evidence(self, evidence: Any) -> str | None:
        normalized = self._normalize_optional_string(evidence)
        if normalized is None:
            return None

        lowered = normalized.lower()

        if lowered == "null":
            return None

        if lowered.startswith("document url:"):
            return None

        if lowered.startswith("document title:"):
            return None

        return normalized
    
    def _is_meaningful_entity(
        self,
        normalized_fields: Dict[str, ExtractedCell],
    ) -> bool:
        name_cell = normalized_fields.get("name")
        if not name_cell or not name_cell.value:
            return False

        filled_non_name_fields = 0
        for field_name, cell in normalized_fields.items():
            if field_name == "name":
                continue
            if cell.value is not None:
                filled_non_name_fields += 1

        # Must have at least 2 meaningful fields
        if filled_non_name_fields < 2:
            return False

        # Must have at least one of these
        if not (
            normalized_fields.get("description").value
            or normalized_fields.get("primary_use_case").value
            or normalized_fields.get("website_or_repo").value
        ):
            return False

        return True