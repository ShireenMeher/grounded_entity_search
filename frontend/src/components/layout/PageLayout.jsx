import { useState } from "react";

export default function PageLayout() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    if (!query.trim()) return;
  
    setLoading(true);
    setError("");
    setHasSearched(true);
  
    try {
      const response = await fetch("http://localhost:8000/discover", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query }),
      });
  
      if (!response.ok) {
        throw new Error("Search request failed");
      }
  
      const data = await response.json();
  
      console.log("BACKEND RESPONSE:", data);
  
      // TEMP: since results are empty in your backend
      setResults(data.results || []);
  
    } catch (err) {
      setError("Something went wrong while fetching results.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-white">
      <div className="flex min-h-screen">
        <aside className="w-68 border-r border-white/10 bg-white/5 p-6">
          <h1 className="text-2xl font-semibold tracking-tight">Nova Studio</h1>
          <p className="mt-2 text-sm text-white/60">
            Search with style.
          </p>

          <nav className="mt-8 space-y-3">
            <div className="rounded-xl bg-white px-4 py-3 text-black">
              Search
            </div>
            <div className="rounded-xl px-4 py-3 text-white/70 hover:bg-white/10">
              Results
            </div>
          </nav>
        </aside>

        <main className="flex-1 p-8">
          <div className="mb-8">
            <h1 className="text-4xl font-semibold tracking-tight">
              Semantic Search
            </h1>
            <p className="mt-2 text-white/60">
              Search across your dataset with fast, relevant results.
            </p>
          </div>

          <div className="mb-8 flex gap-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch();
              }}
              placeholder="Search for vendors, tools, databases..."
              className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-6 py-4 text-lg text-white placeholder:text-white/40 focus:outline-none focus:ring-2 focus:ring-white/20"
            />
            <button
              onClick={handleSearch}
              disabled={loading}
              className="rounded-2xl bg-white px-6 py-4 font-medium text-black hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>

          {error && (
            <div className="mb-6 rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-red-200">
              {error}
            </div>
          )}

          {!hasSearched && (
            <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-white/60">
              Try searching for something to see results.
            </div>
          )}

          {hasSearched && !loading && results.length === 0 && !error && (
            <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-white/60">
              No results found.
            </div>
          )}

          <div className="space-y-4">
            {results.map((item, index) => (
              <div
                key={item.id || item.url || index}
                className="cursor-pointer rounded-2xl border border-white/10 bg-white/5 p-5 transition hover:bg-white/10"
              >
                <h3 className="text-lg font-semibold">
                  {item.title || item.name || "Untitled Result"}
                </h3>

                {(item.snippet || item.description) && (
                  <p className="mt-1 text-sm text-white/60">
                    {item.snippet || item.description}
                  </p>
                )}

                {item.url && (
                  <p className="mt-3 text-sm text-blue-300/80">{item.url}</p>
                )}
              </div>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}