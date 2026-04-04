from collections import defaultdict
import re
from app.models.entity_models import ExtractedEntity, ExtractedCell
from urllib.parse import urlparse

# Trailing words that shouldn't distinguish one entity from another
_TYPE_SUFFIXES = re.compile(
    r"-?(restaurant|pizzeria|pizza|cafe|bar|grill|bakery|bistro|kitchen|"
    r"slice-shop|slice|shop|eatery)$"
)

def _dedup_key(entity_id: str) -> str:
    """Strip trailing type-indicator words so e.g. 'chrissy-s' and 'chrissy-s-pizza' merge."""
    return _TYPE_SUFFIXES.sub("", entity_id).strip("-") or entity_id


class AggregationService:
    def aggregate(self, entities: list[ExtractedEntity], source_ranks: dict[str, int],
                  query: str, entity_type: str,) -> list[ExtractedEntity]:
        grouped: dict[str, list[ExtractedEntity]] = defaultdict(list)

        for entity in entities:
            grouped[_dedup_key(entity.entity_id)].append(entity)

        merged = []
        for entity_id, group in grouped.items():
            merged.append(self._merge_group(group, source_ranks, query, entity_type))

        merged.sort(key=lambda e: e.score, reverse=True)
        return merged

    def _merge_group(self, group: list[ExtractedEntity], source_ranks: dict[str, int], 
                     query: str, entity_type: str,) -> ExtractedEntity:
        base = group[0].model_copy(deep=True)

        for entity in group[1:]:
            base.supporting_sources = list(set(base.supporting_sources + entity.supporting_sources))

            for field_name, incoming_cell in entity.fields.items():
                existing_cell = base.fields.get(field_name)

                if existing_cell is None or existing_cell.value is None:
                    base.fields[field_name] = incoming_cell
                elif incoming_cell.value and existing_cell.value != incoming_cell.value:
                    if self._prefer(incoming_cell, existing_cell):
                        base.fields[field_name] = incoming_cell

        base.score = self._compute_score( base, source_ranks=source_ranks, query=query, entity_type=entity_type,)
        return base

    def _prefer(self, incoming: ExtractedCell, existing: ExtractedCell) -> bool:
        incoming_evidence_len = len(incoming.evidence or "")
        existing_evidence_len = len(existing.evidence or "")
        return incoming_evidence_len > existing_evidence_len

    def _compute_score(
        self,
        entity: ExtractedEntity,
        source_ranks: dict[str, int],
        query: str,
        entity_type: str,
    ) -> float:
        filled_non_name_fields = sum(
            1 for field_name, cell in entity.fields.items()
            if field_name != "name" and cell.value is not None
        )

        best_rank = min(
            (source_ranks.get(url, 999) for url in entity.supporting_sources),
            default=999,
        )

        query_terms = [term.strip().lower() for term in query.split() if term.strip()]
        text_blob = " ".join(
            cell.value for cell in entity.fields.values() if cell.value
        ).lower()

        relevance_score = sum(1 for term in query_terms if term in text_blob)

        official_site_bonus = 2.0 if self._is_official_site(entity) else 0.0
        source_bonus = self._source_type_bonus(entity.supporting_sources)
        entity_type_bonus = self._entity_type_relevance_bonus(entity, entity_type)
        single_source_penalty = self._single_source_penalty(entity)
        evidence_quality = self._evidence_quality_score(entity)

        return (
            2.0 * filled_non_name_fields
            + 1.5 * len(set(entity.supporting_sources))
            + 2.0 * relevance_score
            + official_site_bonus
            + source_bonus
            + entity_type_bonus
            + single_source_penalty
            + evidence_quality
            + max(0, 6 - best_rank)
        )


    def _get_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    def _is_official_site(self, entity: ExtractedEntity) -> bool:
        website = next(
            (entity.fields.get(f) for f in ("website_or_repo", "website", "website_or_listing")
             if entity.fields.get(f) and entity.fields.get(f).value),
            None,
        )
        name_cell = entity.fields.get("name")

        if not website or not website.value or not name_cell or not name_cell.value:
            return False

        domain = self._get_domain(website.value)
        normalized_name = name_cell.value.lower().replace(" ", "").replace("-", "")

        return normalized_name in domain.replace(".", "")
    
    def _source_type_bonus(self, urls: list[str]) -> float:
        bonus = 0.0

        for url in set(urls):
            domain = self._get_domain(url)

            if "github.com" in domain:
                bonus += 1.0
            elif "reddit.com" in domain:
                bonus -= 1.5
            elif domain:
                bonus += 0.5

        return bonus
    
    def _entity_type_relevance_bonus(self, entity: ExtractedEntity, entity_type: str) -> float:
        text_blob = " ".join(
            cell.value for cell in entity.fields.values() if cell.value
        ).lower()

        keywords_by_type = {
            "software_tool": ["database", "sql", "client", "manager", "editor", "admin"],
            "restaurant": ["restaurant", "menu", "food", "cuisine", "dining"],
            "company": ["company", "platform", "business", "startup", "product"],
            "generic_entity": [],
        }

        keywords = keywords_by_type.get(entity_type, [])
        return 0.75 * sum(1 for word in keywords if word in text_blob)
    
    def _evidence_quality_score(self, entity: ExtractedEntity) -> float:
        """
        Score based on the richness of extracted evidence.

        Three signals:
        1. Average evidence length across filled fields — longer snippets mean
           the LLM had more specific text to work with (capped at 2.0).
        2. Coverage — fraction of filled fields that also have evidence
           (penalises entities where values exist but evidence is missing).
        3. Short-evidence penalty — fields with evidence < 15 chars are
           likely noise (e.g. "Yes", "NYC") and drag quality down.
        """
        evidence_lengths: list[int] = []
        fields_with_value = 0
        fields_with_evidence = 0
        short_evidence_count = 0

        for field_name, cell in entity.fields.items():
            if field_name == "name" or cell.value is None:
                continue
            fields_with_value += 1
            if cell.evidence:
                ev_len = len(cell.evidence)
                evidence_lengths.append(ev_len)
                fields_with_evidence += 1
                if ev_len < 15:
                    short_evidence_count += 1

        if not evidence_lengths:
            return 0.0

        avg_len = sum(evidence_lengths) / len(evidence_lengths)
        length_score = min(avg_len / 80.0, 2.0)          # saturates at ~160 chars → 2.0

        coverage = fields_with_evidence / max(fields_with_value, 1)
        coverage_score = coverage * 1.0                    # max +1.0

        short_penalty = -0.3 * short_evidence_count        # each vague field costs 0.3

        return length_score + coverage_score + short_penalty

    def _single_source_penalty(self, entity: ExtractedEntity) -> float:
        if len(set(entity.supporting_sources)) == 1 and not self._is_official_site(entity):
            return -1.0
        return 0.0