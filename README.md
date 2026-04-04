# Grounded — Agentic Entity Search

A system that takes a natural language topic query and returns a structured, source-grounded table of discovered entities from the live web.

**Example queries:**
- `"AI startups in healthcare"` → table of companies with name, website, description, category, location
- `"top pizza places in Brooklyn"` → table of restaurants with name, neighborhood, cuisine, notable feature
- `"open source database tools"` → table of software tools with name, repo, description, open source status
- `"venture capital firms in NYC"` → company table with dynamically chosen fields like focus_area, portfolio_size
- `"best sci-fi novels of 2024"` → generic entity table with author, genre, year

---

## Architecture Overview

```
User Query
    │
    ▼
QueryService          ── LLM classifies entity type + generates schema fields
    │
    ▼
SearchService         ── LLM generates 3 query variants → parallel SerpAPI calls → merge + dedup by URL
    │
    ▼
Snippet Pre-Ranker    ── Scores search results by query term overlap + entity-type keywords + snippet length
    │                    Reorders before scraping so best candidates are scraped first
    ▼
ScrapeService         ── Parallel HTTP fetch + trafilatura text extraction (ThreadPoolExecutor)
    │                    Filters to pages relevant to entity type
    ▼
ExtractionService     ── Parallel GPT-4o-mini calls per page (dynamic schema + dynamic JSON shape)
    │                    Validates: name ≤5 words, ≥2 filled fields
    │                    Hallucination check: verifies evidence is verbatim substring of page text
    ▼
AggregationService    ── Deduplicates by normalised entity ID
    │                    Merges fields across sources (prefers longer evidence)
    │                    Scores on 8 signals: completeness, source count, query relevance,
    │                       official domain match, source authority, entity-type keywords,
    │                       evidence quality, source rank
    ▼
Ranked JSON response  ── Every field carries value + source_url + evidence snippet
    │
    ▼
MetricsStore          ── Records per-query: stage timings, token cost, hallucination rate, scrape failures
```

---

## Design Decisions

### LLM-based query classification with dynamic schema

The system uses GPT-4o-mini to classify each query into an entity type and generate relevant schema fields. A query like `"VC firms focused on climate"` returns `["name", "website", "focus_area", "portfolio_size", "location"]` rather than a fixed company template.

A keyword-matching fallback activates if the LLM call fails, ensuring the pipeline never breaks. The LLM output is validated and sanitised: field names are coerced to snake_case, `"name"` is always first, and the list is capped at 6 fields.

**Why not pure keywords?** Keyword lists fail on anything not explicitly enumerated — `"best pasta spots"`, `"seed-stage B2B tools"`, `"notable alumni"`. The LLM generalises to arbitrary phrasing.

### Multi-query retrieval

Rather than issuing a single search, the system uses GPT-4o-mini to generate 3 query variants (e.g. `"best tacos in LA"` → `"most popular taqueria Los Angeles"` + `"top-rated taco spots LA 2024"`). All variants run in parallel against SerpAPI, results are merged and deduplicated by URL, and low-quality domains (Reddit, Quora, Pinterest) are deprioritised.

**Why?** A single query returns a biased sample of the web. Variants surface different curated lists and authoritative sources that a single phrasing misses.

### Snippet-based pre-ranking before scraping

Before scraping, search results are re-scored using a lightweight signal combining: query term overlap in title + snippet, entity-type keyword presence, snippet length (longer = richer), and domain trust penalties. The top candidates are scraped first.

This runs in <1ms (no LLM), so it adds zero latency while ensuring the scraper invests its limited budget (3 documents) in the most promising pages.

### Grounded extraction — no hallucination by design

The extraction prompt enforces strict grounding rules:
- Only use text explicitly present in the document
- Every field requires both a `value` and an `evidence` snippet copied verbatim from the page
- The JSON response shape is generated dynamically from the actual schema fields, not hardcoded

After extraction, a **hallucination detector** verifies that each evidence string is a real substring of the scraped document text (case-insensitive, whitespace-normalised). Unverified evidence is flagged and the verification rate is reported in the response metadata.

### Entity validation

Two validation gates prevent garbage entities from propagating:
1. **Name length limit** — names longer than 5 words are rejected as taglines, not proper names. This specifically prevents sites like `topstartups.io` (which shows taglines more prominently than names) from producing `"AI automation platform for medical documents"` as an entity name.
2. **Minimum field completeness** — entities with fewer than 2 filled non-name fields are dropped.

### Deduplication with type-aware normalisation

Entity IDs are normalised slugs of the entity name. A regex strips trailing type-indicator words (`pizza`, `restaurant`, `pizzeria`, `cafe`, etc.) before comparison, so `"Chrissy's"` and `"Chrissy's Pizza"` correctly merge rather than creating duplicate rows.

When merging, fields from multiple sources are combined by preferring the cell with the longest evidence (a proxy for richer information). All source URLs are preserved on the merged entity.

### Multi-signal scoring

Entities are ranked by a composite score across 8 signals:

| Signal | Weight | Rationale |
|---|---|---|
| Filled non-name fields | 2.0× per field | Completeness |
| Unique supporting sources | 1.5× per source | Corroboration |
| Query term overlap | 2.0× per term | Relevance |
| Official domain match | +2.0 | Entity has own site |
| Source type (GitHub/Reddit) | ±variable | Authority |
| Entity-type keyword match | +0.75× per keyword | Type relevance |
| Evidence quality | up to +3.0 | Richness of evidence |
| Best source rank | max(0, 6−rank) | Search prominence |
| Single-source penalty | −1.0 | Low corroboration |

**Evidence quality** is a new signal that separates entities with long, specific evidence from those with short or missing evidence. It combines: average evidence length (capped at +2.0), evidence coverage across fields (+1.0), and a per-field penalty for evidence shorter than 15 characters (−0.3 each).

### Parallel scraping and extraction

Both scraping and LLM extraction run in `ThreadPoolExecutor` pools. This brings end-to-end latency from ~140s (original sequential implementation) to ~30–40s.

### Monitoring and observability

Every pipeline run records:
- Per-stage wall-clock timings (search, scrape, extract, aggregate)
- Token counts (input + output) from OpenAI response headers
- Estimated cost in USD (GPT-4o-mini pricing: $0.15/1M input, $0.60/1M output)
- Scrape success/failure counts
- Evidence verification rate (grounding quality)
- Entity counts before and after deduplication

An in-memory ring buffer stores the last 200 query records. `GET /metrics` returns aggregate statistics including average latency, average cost per query, average hallucination rate, and scrape failure rate.

Structured logging uses Python's `logging` module with consistent format `%(asctime)s [%(levelname)s] %(name)s: %(message)s`, giving a per-stage trace of every pipeline run.

---

## Trade-offs & Known Limitations

| Limitation | Detail |
|---|---|
| Single-depth crawling | The system scrapes the pages returned by search but never follows links to entity homepages. Company `website` and `location` fields are often null because list articles don't embed direct URLs inline. A second-pass crawl (fetch entity's own site after finding its name) would fix this. |
| JavaScript rendering | Pages built with React/Next.js return near-empty HTML to `requests`. Affected pages silently produce `fetch_success=False`. A Playwright fallback for pages returning <300 chars of text would cover this. |
| LLM classification cost | Each query now makes 2 LLM calls before any scraping (classification + query expansion). At GPT-4o-mini pricing this adds ~$0.001 per query but increases latency by 1–2s. |
| Multi-query SerpAPI cost | 3 parallel SerpAPI searches per query instead of 1. At ~$0.001/search this triples the search cost to ~$0.003 per query. |
| Schema variability | Dynamic schema means field names vary by query. The aggregation scoring handles any field names, but the frontend renders whatever columns come back. A query returning unusual field names will display correctly but may look sparse. |
| No persistent cache | Repeated identical queries re-run the full pipeline. An in-memory or Redis cache keyed by query string would make re-fetches instant and free. |
| Evidence verification is strict | Hallucination detection uses exact substring matching after whitespace normalisation. Some evidence that is paraphrased rather than copied verbatim (even if accurate) will be marked unverified. This is a conservative measure — false positives are preferable to false negatives for a grounding system. |
| Deduplication is name-based | Two entities with slightly different names (e.g. `"Viz.ai"` vs `"Viz AI"`) won't merge. Fuzzy matching (edit distance or embedding similarity) would improve recall at the cost of precision. |

---

## Setup

### Prerequisites
- Python 3.11+
- Node 18+
- SerpAPI key → [serpapi.com](https://serpapi.com)
- OpenAI API key → [platform.openai.com](https://platform.openai.com)

### Backend

```bash
cd grounded_entity_search
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...
SEARCH_API_KEY=your_serpapi_key
```

Start the API server:

```bash
uvicorn app.main:app --reload
```

API runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

---

## API Reference

### Core endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Aggregate pipeline metrics (latency, cost, hallucination rate) |
| `POST` | `/discover` | **Main endpoint** — full pipeline, returns ranked entity table |

### Debug endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/debug/search` | Search only — returns raw SerpAPI results |
| `POST` | `/debug/scrape` | Search + scrape — returns extracted page text |
| `POST` | `/debug/extract` | Search + scrape + extract — returns entities before aggregation |
| `POST` | `/debug/discover` | Full pipeline with detailed timing breakdown |

### Request body (all POST endpoints)

```json
{ "query": "AI startups in healthcare" }
```

### Response — `/discover`

```json
{
  "query": "AI startups in healthcare",
  "entity_type": "company",
  "schema_fields": ["name", "website", "description", "category", "location"],
  "results": [
    {
      "entity_id": "hippocratic-ai",
      "entity_type": "company",
      "fields": {
        "name": {
          "value": "Hippocratic AI",
          "source_url": "https://hippocraticai.com/",
          "evidence": "Only Hippocratic AI Has Been Clinically Validated on Outputs"
        },
        "website": {
          "value": "https://hippocraticai.com/",
          "source_url": "https://hippocraticai.com/",
          "evidence": "Hippocratic AI | Safest Generative AI Healthcare Agent"
        },
        "description": { "value": "...", "source_url": "...", "evidence": "..." },
        "category": { "value": "Healthcare AI", "source_url": "...", "evidence": "..." },
        "location": { "value": null, "source_url": null, "evidence": null }
      },
      "supporting_sources": ["https://hippocraticai.com/"],
      "score": 22.4
    }
  ],
  "metadata": {
    "search_results_considered": 15,
    "pages_scraped": 12,
    "pages_failed": 3,
    "entities_extracted_before_dedup": 24,
    "entities_after_dedup": 16,
    "hallucination_rate": 0.03,
    "evidence_verified": 58,
    "evidence_total": 60,
    "estimated_cost_usd": 0.0031,
    "stage_timings": {
      "search": 2.1,
      "scrape": 9.4,
      "extract": 18.2,
      "aggregate": 0.04
    }
  },
  "execution_time_seconds": 31.4
}
```

### Response — `GET /metrics`

```json
{
  "total_queries": 12,
  "avg_latency_s": 33.2,
  "avg_entities_returned": 14.6,
  "avg_hallucination_rate": 0.031,
  "avg_scrape_failure_rate": 0.18,
  "total_estimated_cost_usd": 0.038,
  "avg_cost_per_query_usd": 0.0032,
  "avg_stage_timings": {
    "search": 2.3,
    "scrape": 10.1,
    "extract": 19.4,
    "aggregate": 0.05
  },
  "recent": [
    {
      "query": "top pizza places in Brooklyn",
      "entity_type": "restaurant",
      "entities": 21,
      "hallucination_rate": 0.02,
      "cost_usd": 0.0027,
      "time_s": 29.1
    }
  ]
}
```

---

## Project Structure

```
grounded_entity_search/
├── app/
│   ├── main.py                        # FastAPI app + CORS
│   ├── api/
│   │   └── routes.py                  # All HTTP endpoints
│   ├── core/
│   │   ├── config.py                  # Pydantic settings (.env)
│   │   └── logging.py                 # Structured logger factory
│   ├── models/
│   │   ├── entity_models.py           # SearchResult, ScrapedDocument, ExtractedEntity
│   │   ├── request_models.py          # DiscoverRequest
│   │   └── response_models.py         # DiscoverResponse, DiscoverMetadata
│   ├── prompts/
│   │   └── extraction_prompts.py      # Dynamic system + user prompt builders
│   └── services/
│       ├── query_service.py           # LLM query classification + keyword fallback
│       ├── search_service.py          # Multi-query SerpAPI + query expansion
│       ├── scrape_service.py          # Parallel scraping + trafilatura
│       ├── extraction_service.py      # GPT-4o-mini extraction + hallucination detection
│       ├── aggregation_service.py     # Dedup + merge + multi-signal scoring
│       ├── discovery_orchestrator.py  # Pipeline coordinator + snippet pre-ranker
│       └── metrics_store.py           # In-memory metrics ring buffer
├── frontend/
│   └── src/
│       └── components/layout/
│           └── PageLayout.jsx         # Full UI: search, table, evidence tooltips
├── requirements.txt
└── README.md
```
