export const dynamic = "force-dynamic";

import Link from "next/link";
import type { Metadata } from "next";
import { API_BASE } from "@/lib/api";

export const metadata: Metadata = {
  title: "Kalender",
  description: "Fuld kalender over UCI WorldTour-løb i 2026-sæsonen — etaper, startlister og klassementer.",
};

type Race = {
  name: string;
  slug: string;
  start_date: string;
  end_date: string | null;
  country_code: string | null;
  category: string;
  startlist_count: number;
  stage_count: number;
};

type TodayStage = {
  stage_number: number;
  date: string;
  stage_type: string | null;
  start_location: string | null;
  finish_location: string | null;
  distance_km: string | null;
  elevation_image_url: string | null;
};

type OngoingRace = Race & {
  total_stages: number;
  completed_stages: number;
  today_stage: TodayStage | null;
};

async function getOngoingRaces(): Promise<OngoingRace[]> {
  try {
    const res = await fetch(`${API_BASE}/ongoing-races`, { cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

async function getUpcomingRaces(): Promise<Race[]> {
  try {
    const res = await fetch(`${API_BASE}/upcoming-races`, { cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "🌍";
  return code
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5))
    .join("");
}

function formatDate(dateStr: string): string {
  return new Date(dateStr + "T00:00:00").toLocaleDateString("da-DK", {
    day: "numeric",
    month: "long",
  });
}

function daysUntil(dateStr: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(dateStr + "T00:00:00");
  return Math.ceil((d.getTime() - today.getTime()) / 86400000);
}

function daysLeft(endDateStr: string): number {
  return daysUntil(endDateStr);
}

function groupByMonth(races: Race[]): [string, Race[]][] {
  const map = new Map<string, Race[]>();
  for (const race of races) {
    const key = new Date(race.start_date + "T00:00:00").toLocaleDateString("da-DK", {
      month: "long",
      year: "numeric",
    });
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(race);
  }
  return [...map.entries()];
}

const STAGE_TYPE_LABELS: Record<string, string> = {
  flat: "Flad",
  hilly: "Kuperet",
  mountain: "Bjerg",
  tt: "Enkeltstart",
  itt: "Enkeltstart",
};

const STAGE_TYPE_COLORS: Record<string, string> = {
  flat: "text-emerald-400",
  hilly: "text-yellow-400",
  mountain: "text-red-400",
  tt: "text-blue-400",
  itt: "text-blue-400",
};

export default async function RacesPage() {
  const [ongoingRaces, upcomingRaces] = await Promise.all([
    getOngoingRaces(),
    getUpcomingRaces(),
  ]);
  const months = groupByMonth(upcomingRaces);

  return (
    <div className="px-6 py-12">
      <div className="mx-auto max-w-4xl">

        {/* ── Igangværende løb ───────────────────────────────────────────── */}
        {ongoingRaces.length > 0 && (
          <section className="mb-16">
            <div className="flex items-center gap-3 mb-5">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
              </span>
              <h2 className="text-xs uppercase tracking-[0.25em] text-emerald-400 font-medium">
                Igangværende løb
              </h2>
            </div>

            <div className="space-y-4">
              {ongoingRaces.map((race) => {
                const remaining = race.end_date ? daysLeft(race.end_date) : null;
                const pct = race.total_stages > 0
                  ? Math.round((race.completed_stages / race.total_stages) * 100)
                  : 0;
                const ts = race.today_stage;
                const typeLabel = ts?.stage_type ? STAGE_TYPE_LABELS[ts.stage_type] : null;
                const typeColor = ts?.stage_type ? STAGE_TYPE_COLORS[ts.stage_type] : "text-slate-400";

                return (
                  <Link
                    key={race.slug}
                    href={`/${race.slug}`}
                    className="group block rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-slate-900 to-slate-900/60 p-6 hover:border-emerald-500/40 hover:from-slate-900/90 transition-all duration-200"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <span className="text-3xl leading-none">{flagEmoji(race.country_code)}</span>
                        <div>
                          <p className="font-display text-2xl tracking-wide text-white group-hover:text-emerald-300 transition-colors leading-none">
                            {race.name}
                          </p>
                          <p className="text-xs text-slate-500 mt-1">{race.category}</p>
                        </div>
                      </div>
                      {remaining !== null && remaining >= 0 && (
                        <span className="text-xs text-slate-500 flex-shrink-0 ml-4 mt-1">
                          {remaining === 0 ? "Sidste etape i dag" : `${remaining}d tilbage`}
                        </span>
                      )}
                    </div>

                    {ts ? (
                      <div className="mb-4 rounded-xl bg-slate-800/60 border border-slate-700/60 overflow-hidden">
                        {ts.elevation_image_url && (
                          <div className="relative">
                            <img
                              src={ts.elevation_image_url}
                              alt={`Højdeprofil etape ${ts.stage_number}`}
                              className="w-full h-20 object-cover object-bottom"
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 to-transparent" />
                          </div>
                        )}
                        <div className="px-4 py-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 mb-1.5">
                              <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/15 px-2 py-0.5 rounded-full">
                                I dag
                              </span>
                              <span className="text-xs text-slate-500">
                                Etape {ts.stage_number}
                              </span>
                              {typeLabel && (
                                <span className={`text-xs font-medium ${typeColor}`}>
                                  · {typeLabel}
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-emerald-400 font-medium mb-1.5">
                              Se etapen →
                            </span>
                          </div>
                          <p className="text-sm text-slate-200">
                            {ts.start_location}
                            <span className="text-slate-500 mx-1.5">→</span>
                            <span className="font-semibold text-white">{ts.finish_location}</span>
                            {ts.distance_km && (
                              <span className="text-slate-500 ml-2 text-xs font-mono">
                                {parseFloat(ts.distance_km).toFixed(0)} km
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="mb-4 rounded-xl bg-slate-800/40 border border-slate-700/40 px-4 py-3">
                        <p className="text-xs text-slate-500">Hviledag</p>
                      </div>
                    )}

                    <div className="flex items-center gap-3">
                      <div className="flex-1 h-1 rounded-full bg-slate-800 overflow-hidden">
                        <div
                          className="h-full bg-emerald-500 rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-500 flex-shrink-0 tabular-nums">
                        {race.completed_stages} / {race.total_stages} etaper
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* ── Hero ───────────────────────────────────────────────────────── */}
        <header className="mb-14">
          <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">
            UCI WorldTour · Kalender 2026
          </p>
          <h1 className="font-display text-7xl sm:text-9xl tracking-wide leading-none text-white">
            Alle
            <br />
            <span className="text-emerald-400">Løb</span>
          </h1>
          <p className="mt-5 text-slate-400 text-sm max-w-sm leading-relaxed">
            {upcomingRaces.length > 0
              ? `${upcomingRaces.length} løb tilbage i 2026-sæsonen.`
              : ongoingRaces.length > 0
              ? "Alle kommende løb er vist ovenfor."
              : "Opdateres løbende. Start backend-serveren for at se data."}
          </p>
        </header>

        {/* ── Kommende løb ───────────────────────────────────────────────── */}
        {upcomingRaces.length === 0 ? (
          ongoingRaces.length === 0 && (
            <div className="rounded-2xl border border-slate-800 p-16 text-center">
              <p className="text-slate-600 text-sm">Ingen løb fundet.</p>
            </div>
          )
        ) : (
          <div className="space-y-12">
            {months.map(([month, monthRaces]) => (
              <section key={month}>
                <h2 className="font-display text-xl tracking-[0.2em] text-slate-600 uppercase mb-4">
                  {month}
                </h2>
                <div className="space-y-1.5">
                  {monthRaces.map((race) => {
                    const days = daysUntil(race.start_date);
                    const hasStartlist = race.startlist_count > 0;
                    const hasStages = race.stage_count > 0;
                    return (
                      <Link
                        key={race.slug}
                        href={`/${race.slug}`}
                        className="group flex items-center gap-4 rounded-xl border border-slate-800/80 bg-slate-900/40 px-5 py-4 hover:border-emerald-500/40 hover:bg-slate-900 transition-all duration-150"
                      >
                        <span className="text-xl w-8 text-center flex-shrink-0 leading-none">
                          {flagEmoji(race.country_code)}
                        </span>

                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-slate-100 group-hover:text-emerald-400 transition-colors truncate">
                            {race.name}
                          </p>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            <span className="text-xs text-slate-500">
                              {formatDate(race.start_date)}
                            </span>
                            {hasStartlist && (
                              <span className="text-[10px] font-medium text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                                {race.startlist_count} ryttere
                              </span>
                            )}
                            {hasStages && (
                              <span className="text-[10px] font-medium text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">
                                {race.stage_count} etaper
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-2 flex-shrink-0">
                          {days >= 0 && (
                            <span
                              className={`text-xs px-2.5 py-1 rounded-full font-medium tabular-nums ${
                                days === 0
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : days <= 14
                                  ? "bg-emerald-500/10 text-emerald-400"
                                  : "bg-slate-800 text-slate-500"
                              }`}
                            >
                              {days === 0
                                ? "i dag"
                                : days === 1
                                ? "i morgen"
                                : `om ${days}d`}
                            </span>
                          )}
                          <svg
                            className="w-4 h-4 text-slate-700 group-hover:text-emerald-500 transition-colors"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                          </svg>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
