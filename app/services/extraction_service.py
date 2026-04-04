from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from openai import OpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.models.entity_models import ExtractedCell, ExtractedEntity, ScrapedDocument
from app.prompts.extraction_prompts import (
    build_extraction_system_prompt,
    build_extraction_user_prompt,
)

logger = get_logger(__name__)

# GPT-4o-mini pricing (per token)
_COST_INPUT = 0.15 / 1_000_000
_COST_OUTPUT = 0.60 / 1_000_000


class ExtractionService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        # Accumulated across all calls in one pipeline run — reset by orchestrator
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        # Hallucination tracking
        self.evidence_total: int = 0
        self.evidence_verified: int = 0

    def reset_stats(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.evidence_total = 0
        self.evidence_verified = 0

    @property
    def estimated_cost_usd(self) -> float:
        return round(
            self.input_tokens * _COST_INPUT + self.output_tokens * _COST_OUTPUT, 5
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

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

        extracted: List[ExtractedEntity] = []
        for raw_entity in raw_entities:
            entity = self._normalize_entity(
                raw_entity=raw_entity,
                entity_type=entity_type,
                schema_fields=schema_fields,
                document_url=document.url,
                document_text=document.text,
            )
            if entity is not None:
                extracted.append(entity)

        logger.info(
            "extract url=%s parsed=%d accepted=%d tokens_in=%d tokens_out=%d",
            document.url, len(raw_entities), len(extracted),
            self.input_tokens, self.output_tokens,
        )
        return extracted

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if response.usage:
            self.input_tokens += response.usage.prompt_tokens
            self.output_tokens += response.usage.completion_tokens
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _parse_json_response(self, raw_content: str) -> Dict[str, Any] | None:
        if not raw_content.strip():
            return None
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError:
            pass
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                return None
        first, last = raw_content.find("{"), raw_content.rfind("}")
        if first != -1 and last != -1 and first < last:
            try:
                return json.loads(raw_content[first : last + 1])
            except json.JSONDecodeError:
                pass
        return None

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalize_entity(
        self,
        raw_entity: Dict[str, Any],
        entity_type: str,
        schema_fields: List[str],
        document_url: str,
        document_text: str,
    ) -> ExtractedEntity | None:
        if not isinstance(raw_entity, dict):
            return None

        normalized_fields: Dict[str, ExtractedCell] = {}

        for field_name in schema_fields:
            raw_field = raw_entity.get(field_name)
            if isinstance(raw_field, dict):
                value = self._clean_value(field_name, raw_field.get("value"))
                raw_evidence = self._clean_evidence(raw_field.get("evidence"))
                evidence, verified = self._verify_evidence(raw_evidence, document_text)
                if raw_evidence:
                    self.evidence_total += 1
                    if verified:
                        self.evidence_verified += 1
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
        return ExtractedEntity(
            entity_id=self._build_entity_id(name_cell.value, entity_type),
            entity_type=entity_type,
            fields=normalized_fields,
            supporting_sources=[document_url],
            score=0.0,
        )

    # ------------------------------------------------------------------
    # Hallucination detection
    # ------------------------------------------------------------------

    def _verify_evidence(
        self, evidence: str | None, document_text: str
    ) -> Tuple[str | None, bool]:
        """
        Returns (evidence, is_verified).
        Verified means the evidence string appears verbatim in the document
        (case-insensitive, whitespace-normalised).
        """
        if not evidence:
            return None, False

        def _normalise(s: str) -> str:
            return " ".join(s.lower().split())

        norm_evidence = _normalise(evidence)
        norm_doc = _normalise(document_text)

        verified = norm_evidence in norm_doc
        if not verified:
            logger.debug("unverified_evidence snippet=%r", evidence[:80])

        return evidence, verified

    # ------------------------------------------------------------------
    # Field cleaning
    # ------------------------------------------------------------------

    def _build_entity_id(self, name: str, entity_type: str = "") -> str:
        normalized = name.strip().lower()
        if entity_type == "software_tool":
            for phrase in ["community edition", "open source edition", "edition", r"\bcommunity\b"]:
                normalized = re.sub(phrase, "", normalized)
        normalized = normalized.strip()
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
        return normalized.strip("-") or "unknown-entity"

    def _normalize_optional_string(self, value: Any) -> str | None:
        if value is None or not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned if cleaned else None

    def _clean_value(self, field_name: str, value: Any) -> str | None:
        normalized = self._normalize_optional_string(value)
        if normalized is None or normalized.lower() == "null":
            return None
        if field_name == "open_source_status":
            lowered = normalized.strip().lower()
            if lowered in {"open source", "open-source", "free open-source",
                           "free open source", "opensource", "open_source", "true", "yes"}:
                return "open_source"
            if lowered in {"not open source", "closed source", "closed-source", "false", "no"}:
                return "not_open_source"
            return None
        return normalized

    def _clean_evidence(self, evidence: Any) -> str | None:
        normalized = self._normalize_optional_string(evidence)
        if normalized is None or normalized.lower() == "null":
            return None
        lowered = normalized.lower()
        if lowered.startswith("document url:") or lowered.startswith("document title:"):
            return None
        return normalized

    def _is_meaningful_entity(self, normalized_fields: Dict[str, ExtractedCell]) -> bool:
        name_cell = normalized_fields.get("name")
        if not name_cell or not name_cell.value:
            return False
        if len(name_cell.value.split()) > 5:
            return False
        filled_non_name = sum(
            1 for f, c in normalized_fields.items()
            if f != "name" and c.value is not None
        )
        return filled_non_name >= 2
