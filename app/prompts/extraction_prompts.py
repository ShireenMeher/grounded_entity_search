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


def _build_entity_json_shape(schema_fields: List[str]) -> str:
    field_blocks = []
    for field in schema_fields:
        if field == "open_source_status":
            field_blocks.append(
                f'      "{field}": {{\n'
                f'        "value": "open_source | not_open_source | null",\n'
                f'        "evidence": "string or null"\n'
                f'      }}'
            )
        else:
            field_blocks.append(
                f'      "{field}": {{\n'
                f'        "value": "string or null",\n'
                f'        "evidence": "string or null"\n'
                f'      }}'
            )
    fields_str = ",\n".join(field_blocks)
    return '{\n  "entities": [\n    {\n' + fields_str + '\n    }\n  ]\n}'


def build_extraction_user_prompt(
    query: str,
    entity_type: str,
    schema_fields: List[str],
    document_url: str,
    document_title: str | None,
    document_text: str,
) -> str:
    schema_text = ", ".join(schema_fields)
    json_shape = _build_entity_json_shape(schema_fields)

    open_source_rule = (
        '\n8. For "open_source_status", only use one of:\n'
        '   - "open_source"\n'
        '   - "not_open_source"\n'
        '   - null'
        if "open_source_status" in schema_fields
        else ""
    )

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
7. Never output the literal string "null". Use real JSON null.{open_source_rule}
8. If the document does not contain any clearly relevant entities, return:
   {{ "entities": [] }}

Return valid JSON in exactly this shape:
{json_shape}

Important:
- The name field must be the entity's actual proper name (e.g., "Abridge", "Hippocratic AI", "Grimaldi's") — NOT a description, tagline, or mission statement.
- If the document does not state a clear proper name, do not return that entity.
- If name is missing or unsupported, do not return that entity.
- Use only the document text as the evidence source.
"""