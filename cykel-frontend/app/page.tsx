export const revalidate = 60;

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

export const metadata: Metadata = {
  openGraph: {
    url: "/",
    title: "Klassementet — Dansk cykelportal",
    description: "Klassementet er Danmarks bedste cykelportal med etapeinfo, favoritter, højdeprofiler og klassementer fra UCI WorldTour.",
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
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
  stage_start_time: string | null;
};

type OngoingRace = Race & {
  total_stages: number;
  completed_stages: number;
  today_stage: TodayStage | null;
};

type Article = {
  slug: string;
  title: string;
  excerpt: string | null;
  category: string;
  author: string;
  image_url: string | null;
  published_at: string;
  races: { name: string; slug: string } | null;
};

async function getOngoingRaces(): Promise<OngoingRace[]> {
  try {
    const res = await fetch(`${API_BASE}/ongoing-races`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

async function getUpcomingRaces(): Promise<Race[]> {
  try {
    const res = await fetch(`${API_BASE}/upcoming-races`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

async function getLatestArticles(): Promise<Article[]> {
  try {
    const res = await fetch(`${API_BASE}/news?advertorial=false&limit=4`, { next: { revalidate: 60 } });
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

function formatArticleDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", { day: "numeric", month: "short" });
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

const CATEGORY_LABELS: Record<string, string> = {
  resultater: "Resultater",
  startliste: "Startliste",
  transfer: "Transfer",
  profil: "Profil",
  analyse: "Analyse",
  generelt: "Nyheder",
  race_report: "Løbsrapport",
  startlist: "Startliste",
  general: "Nyheder",
  interview: "Interview",
  analysis: "Analyse",
};

const CATEGORY_COLORS: Record<string, string> = {
  resultater: "text-emerald-400",
  startliste: "text-blue-400",
  transfer: "text-yellow-400",
  profil: "text-purple-400",
  analyse: "text-orange-400",
  race_report: "text-red-400",
  interview: "text-cyan-400",
};

const CATEGORY_BG: Record<string, string> = {
  race_report: "from-red-950 to-slate-900",
  resultater:  "from-red-950 to-slate-900",
  startliste:  "from-blue-950 to-slate-900",
  startlist:   "from-blue-950 to-slate-900",
  analyse:     "from-orange-950 to-slate-900",
  analysis:    "from-orange-950 to-slate-900",
  transfer:    "from-yellow-950 to-slate-900",
  profil:      "from-purple-950 to-slate-900",
  interview:   "from-purple-950 to-slate-900",
  generelt:    "from-emerald-950 to-slate-900",
  general:     "from-emerald-950 to-slate-900",
};

const CATEGORY_ICON: Record<string, string> = {
  race_report: "🏆",
  resultater:  "🏆",
  startliste:  "📋",
  startlist:   "📋",
  analyse:     "📊",
  analysis:    "📊",
  transfer:    "🔄",
  profil:      "👤",
  interview:   "🎙️",
  generelt:    "🚴",
  general:     "🚴",
};

export default async function Home() {
  const [ongoingRaces, upcomingRaces, articles] = await Promise.all([
    getOngoingRaces(),
    getUpcomingRaces(),
    getLatestArticles(),
  ]);

  const featuredRaces = upcomingRaces.slice(0, 6);

  return (
    <div className="px-6 py-12">
      <div className="mx-auto max-w-4xl space-y-16">

        {/* ── Igangværende løb ───────────────────────────────────────────── */}
        {ongoingRaces.length > 0 && (
          <section>
            <div className="flex items-center gap-3 mb-5">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
              </span>
              <h2 className="text-xs uppercase tracking-[0.25em] text-emerald-400 font-medium">
                Live
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
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={ts.elevation_image_url}
                            alt={`Højdeprofil etape ${ts.stage_number}`}
                            className="w-full"
                          />
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
                            {ts.stage_start_time && (
                              <span className="text-slate-500 ml-2 text-xs font-mono">
                                · Start {ts.stage_start_time.slice(0, 5)}
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

        {/* ── Vigtige kommende løb ───────────────────────────────────────── */}
        {featuredRaces.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-xs uppercase tracking-[0.25em] text-slate-400 font-medium">
                Kommende løb
              </h2>
              <Link
                href="/races"
                className="text-xs text-slate-600 hover:text-emerald-400 transition-colors"
              >
                Fuld kalender →
              </Link>
            </div>

            <div className="space-y-1.5">
              {featuredRaces.map((race) => {
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
        )}

        {/* ── Seneste nyheder ─────────────────────────────────────────────── */}
        {articles.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-xs uppercase tracking-[0.25em] text-slate-400 font-medium">
                Seneste nyheder
              </h2>
              <Link
                href="/nyheder"
                className="text-xs text-slate-600 hover:text-emerald-400 transition-colors"
              >
                Alle nyheder →
              </Link>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {articles.map((article, i) => {
                const categoryColor = CATEGORY_COLORS[article.category] ?? "text-emerald-400";
                const isLarge = i === 0;

                return (
                  <Link
                    key={article.slug}
                    href={`/nyheder/${article.slug}`}
                    className={`group relative overflow-hidden rounded-2xl border border-slate-800/60 hover:border-emerald-500/30 transition-all duration-200 ${
                      isLarge ? "sm:col-span-2" : ""
                    }`}
                  >
                    <div className={`relative w-full overflow-hidden ${isLarge ? "h-64 sm:h-80" : "h-52"}`}>
                      {article.image_url ? (
                        <>
                          <Image
                            src={article.image_url}
                            alt=""
                            fill
                            sizes="(max-width: 640px) 100vw, 50vw"
                            className="object-cover object-top transition-transform duration-500 group-hover:scale-105"
                            priority={i === 0}
                          />
                          <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/70 to-slate-950/10" />
                        </>
                      ) : (
                        <div className={`absolute inset-0 bg-gradient-to-br ${CATEGORY_BG[article.category] ?? "from-slate-800 to-slate-900"}`}>
                          <span className="absolute bottom-0 right-0 text-[6rem] leading-none opacity-[0.07] select-none pointer-events-none pr-2 pb-0">
                            {CATEGORY_ICON[article.category] ?? "🚴"}
                          </span>
                        </div>
                      )}

                      <div className="absolute inset-0 flex flex-col justify-end p-5">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`text-[10px] uppercase tracking-widest font-semibold ${categoryColor}`}>
                            {CATEGORY_LABELS[article.category] ?? article.category}
                          </span>
                          {article.races && (
                            <span className="text-[10px] text-slate-500">· {article.races.name}</span>
                          )}
                        </div>
                        <h3 className={`font-display tracking-wide leading-tight text-white group-hover:text-emerald-300 transition-colors ${
                          isLarge ? "text-2xl sm:text-3xl" : "text-lg sm:text-xl"
                        }`}>
                          {article.title}
                        </h3>
                        <p className="text-[10px] text-slate-600 mt-2">{formatArticleDate(article.published_at)}</p>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* Empty state — only when nothing to show */}
        {ongoingRaces.length === 0 && featuredRaces.length === 0 && articles.length === 0 && (
          <div className="rounded-2xl border border-slate-800 p-16 text-center">
            <p className="text-slate-600 text-sm">Opdateres løbende — start backend-serveren for at se data.</p>
          </div>
        )}

      </div>
    </div>
  );
}
