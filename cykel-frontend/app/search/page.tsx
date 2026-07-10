export const dynamic = "force-dynamic";

import type { Metadata } from "next";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

export const metadata: Metadata = { title: "Søg" };

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

async function getSearchResults(q: string): Promise<SearchResults | null> {
  if (!q || q.length < 2) return null;
  try {
    const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "🌍";
  return code.toUpperCase().split("").map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)).join("");
}

const SPECIALITY_COLORS: Record<string, string> = {
  Climber: "text-red-400",
  Sprinter: "text-green-400",
  "Time trialist": "text-blue-400",
  "All-rounder": "text-purple-400",
  Puncheur: "text-orange-400",
};

export default async function SearchPage(props: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await props.searchParams;
  const results = q ? await getSearchResults(q) : null;

  const total = results
    ? results.riders.length + results.races.length + results.teams.length + results.climbs.length
    : 0;

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <header className="mb-10">
        <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">
          Klassementet
        </p>
        <h1 className="font-display text-5xl sm:text-7xl tracking-wide leading-none text-white mb-4">
          {q ? `"${q}"` : "Søg"}
        </h1>
        {q && results && (
          <p className="text-sm text-slate-500">
            {total === 0 ? "Ingen resultater fundet." : `${total} resultat${total !== 1 ? "er" : ""} fundet`}
          </p>
        )}
      </header>

      {!q && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center">
          <p className="text-slate-500 text-sm">Brug søgefeltet i toppen (Ctrl+K) for at søge.</p>
        </div>
      )}

      {results && total === 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center">
          <p className="text-slate-500 text-sm mb-2">Ingen resultater for &quot;{q}&quot;</p>
          <p className="text-slate-700 text-xs">Prøv et andet søgeord — ryttere, løb, hold eller stigninger.</p>
        </div>
      )}

      {results && total > 0 && (
        <div className="space-y-10">

          {/* Ryttere */}
          {results.riders.length > 0 && (
            <section>
              <h2 className="text-xs uppercase tracking-[0.2em] text-slate-600 font-medium mb-3">
                Ryttere · {results.riders.length}
              </h2>
              <div className="space-y-1.5">
                {results.riders.map((r) => (
                  <Link
                    key={r.slug}
                    href={`/riders/${r.slug}`}
                    className="group flex items-center gap-4 rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3 hover:border-emerald-500/40 hover:bg-slate-900 transition-all duration-150"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-100 group-hover:text-emerald-400 transition-colors truncate">
                        {r.name}
                      </p>
                      {r.speciality && (
                        <span className={`text-xs ${SPECIALITY_COLORS[r.speciality] ?? "text-slate-500"}`}>
                          {r.speciality}
                        </span>
                      )}
                    </div>
                    {r.nationality && (
                      <span className="text-lg flex-shrink-0">{flagEmoji(r.nationality)}</span>
                    )}
                    <svg className="w-4 h-4 text-slate-700 group-hover:text-emerald-500 transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Løb */}
          {results.races.length > 0 && (
            <section>
              <h2 className="text-xs uppercase tracking-[0.2em] text-slate-600 font-medium mb-3">
                Løb · {results.races.length}
              </h2>
              <div className="space-y-1.5">
                {results.races.map((r) => (
                  <Link
                    key={r.slug}
                    href={`/${r.slug}`}
                    className="group flex items-center gap-4 rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3 hover:border-emerald-500/40 hover:bg-slate-900 transition-all duration-150"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-100 group-hover:text-emerald-400 transition-colors truncate">
                        {r.name}
                      </p>
                      <span className="text-xs text-slate-500">{r.category}</span>
                    </div>
                    {r.start_date && (
                      <span className="text-xs text-slate-600 flex-shrink-0 font-mono">
                        {new Date(r.start_date + "T00:00:00").getFullYear()}
                      </span>
                    )}
                    <svg className="w-4 h-4 text-slate-700 group-hover:text-emerald-500 transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Hold */}
          {results.teams.length > 0 && (
            <section>
              <h2 className="text-xs uppercase tracking-[0.2em] text-slate-600 font-medium mb-3">
                Hold · {results.teams.length}
              </h2>
              <div className="space-y-1.5">
                {results.teams.map((t) => (
                  <Link
                    key={t.slug}
                    href={`/teams/${t.slug}`}
                    className="group flex items-center gap-4 rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3 hover:border-emerald-500/40 hover:bg-slate-900 transition-all duration-150"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-100 group-hover:text-emerald-400 transition-colors truncate">
                        {t.name}
                      </p>
                    </div>
                    {t.country_code && (
                      <span className="text-lg flex-shrink-0">{flagEmoji(t.country_code)}</span>
                    )}
                    <svg className="w-4 h-4 text-slate-700 group-hover:text-emerald-500 transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Stigninger */}
          {results.climbs.length > 0 && (
            <section>
              <h2 className="text-xs uppercase tracking-[0.2em] text-slate-600 font-medium mb-3">
                Stigninger · {results.climbs.length}
              </h2>
              <div className="space-y-1.5">
                {results.climbs.map((c, i) => {
                  const race = c.stages?.races;
                  // Peger på løbssiden, ikke den specifikke etapeside — undgår 404
                  // for historiske etaper, som ikke længere har egen landingsside.
                  const href = race ? `/${race.slug}` : "#";
                  return (
                    <Link
                      key={i}
                      href={href}
                      className="group flex items-center gap-4 rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3 hover:border-emerald-500/40 hover:bg-slate-900 transition-all duration-150"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-slate-100 group-hover:text-emerald-400 transition-colors truncate">
                          {c.name}
                        </p>
                        {race && (
                          <span className="text-xs text-slate-500">
                            {race.name} · Etape {c.stages?.stage_number}
                          </span>
                        )}
                      </div>
                      <svg className="w-4 h-4 text-slate-700 group-hover:text-emerald-500 transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

        </div>
      )}
    </div>
  );
}
