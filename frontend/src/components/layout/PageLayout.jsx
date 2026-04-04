import { useState } from "react";
import { Search, ExternalLink, Clock, Globe, Database, Loader2, AlertCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

function formatFieldName(field) {
  return field
    .replace(/_or_/g, " / ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function EntityTypeTag({ type }) {
  const styles = {
    restaurant: "bg-orange-500/10 text-orange-300 border-orange-500/20",
    company: "bg-blue-500/10 text-blue-300 border-blue-500/20",
    software_tool: "bg-violet-500/10 text-violet-300 border-violet-500/20",
    generic_entity: "bg-neutral-500/10 text-neutral-400 border-neutral-500/20",
  };
  const labels = {
    restaurant: "Restaurant",
    company: "Company",
    software_tool: "Software",
    generic_entity: "Entity",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        styles[type] ?? styles.generic_entity
      }`}
    >
      {labels[type] ?? type}
    </span>
  );
}

function EvidenceTooltip({ evidence, sourceUrl }) {
  return (
    <div className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl border border-white/10 bg-neutral-900/95 p-3 shadow-2xl backdrop-blur-sm">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-white/30">
        Evidence
      </p>
      <p className="text-xs leading-relaxed text-white/65 italic">
        &ldquo;{evidence}&rdquo;
      </p>
      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 flex items-center gap-1 text-[10px] text-blue-400/60 hover:text-blue-400 transition-colors truncate"
        >
          <ExternalLink size={9} />
          {sourceUrl.replace(/^https?:\/\//, "").split("/")[0]}
        </a>
      )}
    </div>
  );
}

function EntityCell({ cell }) {
  const [showEvidence, setShowEvidence] = useState(false);

  if (!cell?.value) {
    return <span className="text-white/15 text-sm">—</span>;
  }

  const isUrl =
    typeof cell.value === "string" && cell.value.startsWith("http");

  return (
    <div
      className="relative"
      onMouseEnter={() => cell.evidence && setShowEvidence(true)}
      onMouseLeave={() => setShowEvidence(false)}
    >
      <div className="flex items-start gap-1.5">
        {isUrl ? (
          <a
            href={cell.value}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 text-sm underline underline-offset-2 transition-colors truncate max-w-[180px]"
          >
            {cell.value.replace(/^https?:\/\//, "").replace(/\/$/, "")}
          </a>
        ) : (
          <span
            className={`text-sm leading-snug ${
              cell.evidence ? "cursor-help text-white/85" : "text-white/85"
            }`}
          >
            {cell.value}
          </span>
        )}
        {cell.source_url && (
          <a
            href={cell.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-0.5 shrink-0 text-white/15 hover:text-white/50 transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink size={10} />
          </a>
        )}
      </div>

      <AnimatePresence>
        {showEvidence && cell.evidence && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
          >
            <EvidenceTooltip
              evidence={cell.evidence}
              sourceUrl={cell.source_url}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SkeletonRow({ cols }) {
  return (
    <tr className="border-b border-white/[0.04]">
      <td className="px-5 py-4">
        <div className="h-3 w-4 rounded bg-white/5 animate-pulse" />
      </td>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-5 py-4">
          <div
            className="h-3 rounded bg-white/5 animate-pulse"
            style={{ width: `${50 + Math.random() * 40}%` }}
          />
        </td>
      ))}
      <td className="px-5 py-4">
        <div className="h-3 w-24 rounded bg-white/5 animate-pulse" />
      </td>
    </tr>
  );
}

const EXAMPLE_QUERIES = [
  "AI startups in healthcare",
  "top pizza places in Brooklyn",
  "open source database tools",
  "fintech companies in New York",
];

export default function PageLayout() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async (q = query) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setLoading(true);
    setError("");
    setResults(null);

    try {
      const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${API}/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setResults(data);
    } catch {
      setError("Search failed. Make sure the backend is running on port 8000.");
    } finally {
      setLoading(false);
    }
  };

  const schemaFields = results?.schema_fields ?? [];
  const entities = results?.results ?? [];
  const meta = results?.metadata;

  return (
    <div className="min-h-screen bg-[#07070f] text-white">
      {/* Top bar */}
      <header className="sticky top-0 z-40 border-b border-white/[0.05] bg-[#07070f]/80 backdrop-blur-md px-8 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-blue-600 shadow-lg shadow-violet-500/20">
              <Database size={14} className="text-white" />
            </div>
            <span className="text-base font-semibold tracking-tight">Grounded</span>
            <span className="text-xs text-white/25 font-normal hidden sm:inline">
              / entity search
            </span>
          </div>
          <span className="text-xs text-white/20 hidden sm:block">
            GPT-4o-mini · SerpAPI · trafilatura
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-14">
        {/* Hero */}
        <div className="mb-12 text-center">
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-5xl font-bold tracking-tight"
          >
            <span className="bg-gradient-to-r from-white via-white/90 to-white/40 bg-clip-text text-transparent">
              Discover anything
            </span>
            <br />
            <span className="bg-gradient-to-r from-violet-400 to-blue-400 bg-clip-text text-transparent">
              from the web.
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mt-4 text-white/40 text-lg"
          >
            Structured entity extraction with source-grounded evidence.
          </motion.p>
        </div>

        {/* Search */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mx-auto mb-5 flex max-w-2xl items-center gap-3"
        >
          <div className="relative flex-1">
            <Search
              size={16}
              className="absolute left-4 top-1/2 -translate-y-1/2 text-white/25"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder='e.g. "AI startups in healthcare"'
              className="w-full rounded-2xl border border-white/[0.08] bg-white/[0.03] py-4 pl-11 pr-4 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-violet-500/40 focus:ring-2 focus:ring-violet-500/20 transition-all"
            />
          </div>
          <button
            onClick={() => handleSearch()}
            disabled={loading || !query.trim()}
            className="flex items-center gap-2 rounded-2xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed px-6 py-4 text-sm font-semibold text-white transition-colors shadow-lg shadow-violet-600/20"
          >
            {loading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Search size={15} />
            )}
            Search
          </button>
        </motion.div>

        {/* Example queries */}
        {!results && !loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="mb-12 flex flex-wrap justify-center gap-2"
          >
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => handleSearch(q)}
                className="rounded-full border border-white/[0.07] bg-white/[0.03] px-4 py-1.5 text-xs text-white/40 hover:text-white/70 hover:border-white/15 hover:bg-white/[0.05] transition-all"
              >
                {q}
              </button>
            ))}
          </motion.div>
        )}

        {/* Error */}
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mb-6 flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/8 p-4 text-sm text-red-300"
          >
            <AlertCircle size={15} className="shrink-0" />
            {error}
          </motion.div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="h-5 w-20 rounded-full bg-white/5 animate-pulse" />
              <div className="h-3 w-32 rounded bg-white/5 animate-pulse" />
            </div>
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/[0.06] bg-white/[0.02]">
                    {Array.from({ length: 7 }).map((_, i) => (
                      <th key={i} className="px-5 py-3.5">
                        <div className="h-2.5 w-16 rounded bg-white/5 animate-pulse" />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <SkeletonRow key={i} cols={5} />
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-center text-xs text-white/20 pt-2">
              Searching the web, scraping pages, extracting entities… ~30s
            </p>
          </motion.div>
        )}

        {/* Results */}
        <AnimatePresence>
          {results && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
            >
              {/* Meta bar */}
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-3">
                  <EntityTypeTag type={results.entity_type} />
                  <span className="text-sm text-white/40">
                    <span className="font-medium text-white/70">
                      {entities.length}
                    </span>{" "}
                    entities
                  </span>
                  {meta && (
                    <>
                      <span className="text-white/15">·</span>
                      <span className="flex items-center gap-1.5 text-sm text-white/35">
                        <Globe size={12} />
                        {meta.pages_scraped} pages scraped
                        {meta.pages_failed > 0 && (
                          <span className="text-red-400/60">({meta.pages_failed} failed)</span>
                        )}
                      </span>
                      <span className="text-white/15">·</span>
                      <span className="flex items-center gap-1.5 text-sm text-white/35">
                        <Clock size={12} />
                        {results.execution_time_seconds?.toFixed(1)}s
                      </span>
                      {meta.hallucination_rate != null && (
                        <>
                          <span className="text-white/15">·</span>
                          <span
                            className={`text-xs font-medium ${
                              meta.hallucination_rate < 0.1
                                ? "text-emerald-400/60"
                                : meta.hallucination_rate < 0.3
                                ? "text-yellow-400/60"
                                : "text-red-400/60"
                            }`}
                            title={`${meta.evidence_verified}/${meta.evidence_total} evidence cells verified`}
                          >
                            {Math.round((1 - meta.hallucination_rate) * 100)}% grounded
                          </span>
                        </>
                      )}
                      {meta.estimated_cost_usd != null && (
                        <>
                          <span className="text-white/15">·</span>
                          <span className="text-xs text-white/25">
                            ${meta.estimated_cost_usd.toFixed(4)}
                          </span>
                        </>
                      )}
                    </>
                  )}
                </div>
                <span className="text-xs text-white/20 italic">
                  Hover a cell to see its source evidence
                </span>
              </div>

              {entities.length === 0 ? (
                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-16 text-center text-white/25">
                  No entities found for this query. Try rephrasing.
                </div>
              ) : (
                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="border-b border-white/[0.06] bg-white/[0.025]">
                        <th className="px-5 py-3.5 text-left text-[10px] font-semibold uppercase tracking-widest text-white/25 w-8">
                          #
                        </th>
                        {schemaFields.map((field) => (
                          <th
                            key={field}
                            className="px-5 py-3.5 text-left text-[10px] font-semibold uppercase tracking-widest text-white/25 whitespace-nowrap"
                          >
                            {formatFieldName(field)}
                          </th>
                        ))}
                        <th className="px-5 py-3.5 text-left text-[10px] font-semibold uppercase tracking-widest text-white/25">
                          Sources
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {entities.map((entity, idx) => (
                        <motion.tr
                          key={entity.entity_id}
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: idx * 0.03, duration: 0.25 }}
                          className="border-b border-white/[0.04] hover:bg-white/[0.025] transition-colors"
                        >
                          <td className="px-5 py-4 text-white/20 text-xs align-top">
                            {idx + 1}
                          </td>
                          {schemaFields.map((field) => (
                            <td
                              key={field}
                              className="px-5 py-4 align-top max-w-[220px]"
                            >
                              <EntityCell cell={entity.fields?.[field]} />
                            </td>
                          ))}
                          <td className="px-5 py-4 align-top">
                            <div className="flex flex-col gap-1.5">
                              {[...new Set(entity.supporting_sources)].map(
                                (src) => (
                                  <a
                                    key={src}
                                    href={src}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1 text-[11px] text-white/25 hover:text-white/55 transition-colors truncate max-w-[140px]"
                                  >
                                    <ExternalLink size={9} />
                                    {src
                                      .replace(/^https?:\/\//, "")
                                      .split("/")[0]}
                                  </a>
                                )
                              )}
                            </div>
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
