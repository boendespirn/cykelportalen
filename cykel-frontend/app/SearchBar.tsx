"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";

type SearchResults = {
  riders: Array<{ name: string; slug: string; nationality: string | null; speciality: string | null }>;
  races: Array<{ name: string; slug: string; start_date: string; category: string }>;
  teams: Array<{ name: string; slug: string; country_code: string | null }>;
  climbs: Array<{
    name: string;
    stage_id: string;
    stages: { stage_number: number; races: { name: string; slug: string } } | null;
  }>;
};

export default function SearchBar() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
      setResults(null);
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setResults(null);
      return;
    }
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query.trim())}`);
        if (res.ok) setResults(await res.json());
      } catch {}
      setLoading(false);
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const totalResults = results
    ? results.riders.length + results.races.length + results.teams.length + results.climbs.length
    : 0;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 text-slate-500 hover:text-slate-200 transition-colors"
        title="Søg (Ctrl+K)"
        aria-label="Åbn søgning"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <kbd className="hidden sm:inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border border-slate-700 text-slate-600 font-sans">
          <span className="text-[9px]">⌘</span>K
        </kbd>
      </button>

      {open && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-40"
            onClick={() => setOpen(false)}
          />

          {/* Modal */}
          <div className="fixed top-[12%] left-1/2 -translate-x-1/2 w-full max-w-lg z-50 px-4">
            <div className="rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
              {/* Input row */}
              <div className="flex items-center gap-3 px-4 border-b border-slate-800">
                <svg className="w-4 h-4 text-slate-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && query.trim()) {
                      router.push(`/search?q=${encodeURIComponent(query.trim())}`);
                      setOpen(false);
                    }
                  }}
                  placeholder="Søg ryttere, løb, hold, stigninger..."
                  className="flex-1 py-4 bg-transparent text-white placeholder:text-slate-600 outline-none text-sm"
                />
                {loading ? (
                  <div className="w-4 h-4 border-2 border-slate-700 border-t-emerald-400 rounded-full animate-spin flex-shrink-0" />
                ) : null}
                <button
                  onClick={() => setOpen(false)}
                  className="text-[10px] text-slate-600 hover:text-slate-400 px-1.5 py-0.5 border border-slate-700 rounded transition-colors"
                >
                  ESC
                </button>
              </div>

              {/* Results */}
              {results && totalResults > 0 && (
                <div className="max-h-80 overflow-y-auto py-2">
                  {results.riders.length > 0 && (
                    <ResultGroup label="Ryttere">
                      {results.riders.map((r) => (
                        <ResultItem key={r.slug} href={`/riders/${r.slug}`} onClick={() => setOpen(false)}>
                          <span className="text-sm text-slate-200">{r.name}</span>
                          {r.speciality && <span className="text-xs text-slate-500">{r.speciality}</span>}
                        </ResultItem>
                      ))}
                    </ResultGroup>
                  )}

                  {results.races.length > 0 && (
                    <ResultGroup label="Løb">
                      {results.races.map((r) => (
                        <ResultItem key={r.slug} href={`/${r.slug}`} onClick={() => setOpen(false)}>
                          <span className="text-sm text-slate-200">{r.name}</span>
                          {r.start_date && (
                            <span className="text-xs text-slate-500">
                              {new Date(r.start_date + "T00:00:00").getFullYear()}
                            </span>
                          )}
                        </ResultItem>
                      ))}
                    </ResultGroup>
                  )}

                  {results.teams.length > 0 && (
                    <ResultGroup label="Hold">
                      {results.teams.map((t) => (
                        <ResultItem key={t.slug} href={`/teams/${t.slug}`} onClick={() => setOpen(false)}>
                          <span className="text-sm text-slate-200">{t.name}</span>
                        </ResultItem>
                      ))}
                    </ResultGroup>
                  )}

                  {results.climbs.length > 0 && (
                    <ResultGroup label="Stigninger">
                      {results.climbs.map((c, i) => {
                        const race = c.stages?.races;
                        const href = race
                          ? `/${race.slug}/stage/${c.stages?.stage_number}`
                          : "#";
                        return (
                          <ResultItem key={i} href={href} onClick={() => setOpen(false)}>
                            <span className="text-sm text-slate-200">{c.name}</span>
                            {race && <span className="text-xs text-slate-500">{race.name}</span>}
                          </ResultItem>
                        );
                      })}
                    </ResultGroup>
                  )}
                </div>
              )}

              {results && totalResults === 0 && query.length >= 2 && !loading && (
                <div className="px-4 py-6 text-center text-sm text-slate-600">
                  Ingen resultater for &quot;{query}&quot;
                </div>
              )}

              {!results && !loading && (
                <div className="px-4 py-3 flex items-center justify-between">
                  <span className="text-xs text-slate-700">Søg i ryttere, løb, hold og stigninger</span>
                  <span className="text-[10px] text-slate-700">Enter for fuld søgning</span>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

function ResultGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="px-2 mb-1">
      <p className="px-2 py-1 text-[10px] uppercase tracking-widest text-slate-600 font-medium">{label}</p>
      {children}
    </div>
  );
}

function ResultItem({
  href,
  onClick,
  children,
}: {
  href: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors gap-2"
    >
      <div className="flex items-center gap-3 min-w-0">{children}</div>
      <svg
        className="w-3 h-3 text-slate-700 flex-shrink-0"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
      </svg>
    </Link>
  );
}
