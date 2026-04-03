from typing import List


def build_extraction_system_prompt() -> str:
    return (
        "You extract structured entities from web page text.\n"
        "You must only use information explicitly stated in the provided document text.\n"
        "Do not use outside knowledge.\n"
        "Do not infer missing values.\n"
        "Do not copy instructions or prompt text into the output.\n"
        "Do not use the document URL, document title, or schema names as evidence unless they appear verbatim in the document text.\n"
        "If a field is not explicitly supported by the document text, set both value and evidence to null.\n"
        "Return valid JSON only.\n"
    )


def build_extraction_user_prompt(
    query: str,
    entity_type: str,
    schema_fields: List[str],
    document_url: str,
    document_title: str | None,
    document_text: str,
) -> str:
    schema_text = ", ".join(schema_fields)

    return f"""
User query:
{query}

Target entity type:
{entity_type}

Schema fields:
{schema_text}

Document URL:
{document_url}

Document title:
{document_title or "Unknown"}

Document text:
\"\"\"
{document_text}
\"\"\"

Task:
Extract entities relevant to the user query from this document only.

Strict rules:
1. Only extract entities explicitly mentioned in the document text.
2. Only extract entities relevant to the user query.
3. Include all schema fields for every entity.
4. If a field is not explicitly supported by the document text, return:
   {{
     "value": null,
     "evidence": null
   }}
5. Evidence must be a short exact snippet copied from the document text.
6. Never use:
   - "Document URL: ..."
   - "Document title: ..."
   - schema names
   - explanations outside the document text
   as evidence.
7. Never output the literal string "null". Use real JSON null.
8. For "open_source_status", only use one of:
   - "open_source"
   - "not_open_source"
   - null
9. If the document does not contain any clearly relevant entities, return:
   {{ "entities": [] }}

Return valid JSON in exactly this shape:
{{
  "entities": [
    {{
      "name": {{
        "value": "string or null",
        "evidence": "string or null"
      }},
      "website_or_repo": {{
        "value": "string or null",
        "evidence": "string or null"
      }},
      "description": {{
        "value": "string or null",
        "evidence": "string or null"
      }},
      "open_source_status": {{
        "value": "open_source | not_open_source | null",
        "evidence": "string or null"
      }},
      "primary_use_case": {{
        "value": "string or null",
        "evidence": "string or null"
      }}
    }}
  ]
}}

Important:
- The name field must identify the entity.
- If name is missing or unsupported, do not return that entity.
- Use only the document text as the evidence source.
"""