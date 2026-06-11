export const revalidate = 60;

import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

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
  } catch { return []; }
}

async function getUpcomingRaces(): Promise<Race[]> {
  try {
    const res = await fetch(`${API_BASE}/upcoming-races`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

async function getLatestArticles(): Promise<Article[]> {
  try {
    const res = await fetch(`${API_BASE}/news?advertorial=false&limit=4`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "🌍";
  return code.toUpperCase().split("").map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)).join("");
}

function formatDate(dateStr: string): string {
  return new Date(dateStr + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "long" });
}

function formatArticleDate(d: string): string {
  return new Date(d).toLocaleDateString("da-DK", { day: "numeric", month: "short" });
}

function daysUntil(dateStr: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.ceil((new Date(dateStr + "T00:00:00").getTime() - today.getTime()) / 86400000);
}

function daysLeft(endDateStr: string): number {
  return daysUntil(endDateStr);
}

const STAGE_TYPE_LABELS: Record<string, string> = {
  flat: "Flad", hilly: "Kuperet", mountain: "Bjerg", tt: "Enkeltstart", itt: "Enkeltstart",
};

const STAGE_TYPE_COLORS: Record<string, string> = {
  flat: "#22c55e", hilly: "#f59e0b", mountain: "#ef4444", tt: "#60a5fa", itt: "#60a5fa",
};

const CATEGORY_LABELS: Record<string, string> = {
  resultater: "Resultater", startliste: "Startliste", transfer: "Transfer",
  profil: "Profil", analyse: "Analyse", generelt: "Nyheder", race_report: "Løbsrapport",
  startlist: "Startliste", general: "Nyheder", interview: "Interview", analysis: "Analyse",
};

const CATEGORY_COLORS: Record<string, string> = {
  resultater: "#e63946", startliste: "#60a5fa", transfer: "#f59e0b",
  profil: "#a78bfa", analyse: "#fb923c", race_report: "#e63946",
  interview: "#22d3ee", general: "#4ade80", generelt: "#4ade80", analysis: "#fb923c",
};

const CATEGORY_GRADIENT: Record<string, string> = {
  race_report: "from-red-950/80 to-slate-950",
  resultater: "from-red-950/80 to-slate-950",
  startliste: "from-blue-950/80 to-slate-950",
  startlist: "from-blue-950/80 to-slate-950",
  analyse: "from-orange-950/80 to-slate-950",
  analysis: "from-orange-950/80 to-slate-950",
  transfer: "from-amber-950/80 to-slate-950",
  profil: "from-purple-950/80 to-slate-950",
  interview: "from-cyan-950/80 to-slate-950",
  generelt: "from-slate-900 to-slate-950",
  general: "from-slate-900 to-slate-950",
};

function SectionHeader({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div className="flex items-center gap-3">
        <span className="block w-0.5 h-4 rounded-full flex-shrink-0" style={{ background: "var(--accent)" }} />
        <h2 className="text-xs font-semibold uppercase tracking-[0.22em]" style={{ color: "var(--text-2)" }}>
          {children}
        </h2>
      </div>
      {action}
    </div>
  );
}

function LiveDot() {
  return (
    <span className="flex items-center gap-1.5">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: "var(--live)" }} />
        <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: "var(--live)" }} />
      </span>
      <span className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: "var(--live)" }}>
        Live
      </span>
    </span>
  );
}

export default async function Home() {
  const [ongoingRaces, upcomingRaces, articles] = await Promise.all([
    getOngoingRaces(),
    getUpcomingRaces(),
    getLatestArticles(),
  ]);

  const featuredRaces = upcomingRaces.slice(0, 8);

  return (
    <div className="px-6 py-12">
      <div className="mx-auto max-w-4xl space-y-20">

        {/* ══ LIVE RACES ═══════════════════════════════════════════════════ */}
        {ongoingRaces.length > 0 && (
          <section>
            <SectionHeader action={<LiveDot />}>I gang nu</SectionHeader>

            <div className="space-y-5">
              {ongoingRaces.map((race) => {
                const remaining = race.end_date ? daysLeft(race.end_date) : null;
                const pct = race.total_stages > 0
                  ? Math.round((race.completed_stages / race.total_stages) * 100)
                  : 0;
                const ts = race.today_stage;
                const typeLabel = ts?.stage_type ? STAGE_TYPE_LABELS[ts.stage_type] : null;
                const typeColor = ts?.stage_type ? STAGE_TYPE_COLORS[ts.stage_type] : "var(--text-2)";

                return (
                  <Link
                    key={race.slug}
                    href={`/${race.slug}`}
                    className="group block rounded-2xl overflow-hidden transition-all duration-200"
                    style={{
                      background: "var(--surface)",
                      border: "1px solid var(--accent-border)",
                      boxShadow: "0 0 48px var(--accent-glow)",
                    }}
                  >
                    {/* Elevation hero */}
                    {ts?.elevation_image_url && (
                      <div className="relative w-full overflow-hidden" style={{ background: "var(--surface-2)" }}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={ts.elevation_image_url}
                          alt={`Højdeprofil etape ${ts.stage_number}`}
                          className="w-full block"
                          style={{ maxHeight: "180px", objectFit: "cover", objectPosition: "bottom" }}
                        />
                        <div
                          className="absolute inset-0 flex items-start justify-between p-4"
                          style={{ background: "linear-gradient(to bottom, rgba(6,9,26,0.88) 0%, transparent 65%)" }}
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-2xl leading-none">{flagEmoji(race.country_code)}</span>
                            <div>
                              <p className="font-display text-3xl sm:text-4xl leading-none text-white tracking-wide">
                                {race.name}
                              </p>
                              <p className="text-[11px] mt-1 font-medium" style={{ color: "var(--text-2)" }}>
                                {race.category}
                              </p>
                            </div>
                          </div>
                          {remaining !== null && remaining >= 0 && (
                            <span
                              className="text-[11px] font-mono px-2.5 py-1 rounded-lg flex-shrink-0 ml-4"
                              style={{
                                background: "rgba(6,9,26,0.75)",
                                color: "var(--text-2)",
                                border: "1px solid var(--border)",
                              }}
                            >
                              {remaining === 0 ? "Sidste etape" : `${remaining}d tilbage`}
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    <div className="px-5 py-4">
                      {/* Fallback header when no elevation image */}
                      {!ts?.elevation_image_url && (
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-3">
                            <span className="text-2xl leading-none">{flagEmoji(race.country_code)}</span>
                            <div>
                              <p className="font-display text-3xl leading-none text-white tracking-wide">{race.name}</p>
                              <p className="text-[11px] mt-1" style={{ color: "var(--text-2)" }}>{race.category}</p>
                            </div>
                          </div>
                          {remaining !== null && remaining >= 0 && (
                            <span className="text-xs font-mono" style={{ color: "var(--text-2)" }}>
                              {remaining === 0 ? "Sidste etape" : `${remaining}d tilbage`}
                            </span>
                          )}
                        </div>
                      )}

                      {/* Today's stage strip */}
                      {ts ? (
                        <div
                          className="rounded-xl px-4 py-3 mb-4"
                          style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2.5 flex-wrap">
                              <span
                                className="text-[10px] font-bold uppercase tracking-[0.18em] px-2.5 py-0.5 rounded-full"
                                style={{
                                  background: "var(--accent-dim)",
                                  color: "var(--accent)",
                                  border: "1px solid var(--accent-border)",
                                }}
                              >
                                I dag · Etape {ts.stage_number}
                              </span>
                              {typeLabel && (
                                <span className="text-xs font-medium" style={{ color: typeColor }}>
                                  {typeLabel}
                                </span>
                              )}
                            </div>
                            <span className="text-[11px] font-medium transition-colors" style={{ color: "var(--accent)" }}>
                              Se etapen →
                            </span>
                          </div>
                          <p className="text-sm">
                            <span style={{ color: "var(--text-2)" }}>{ts.start_location}</span>
                            <span className="mx-2" style={{ color: "var(--text-3)" }}>→</span>
                            <span className="font-semibold text-white">{ts.finish_location}</span>
                            {ts.distance_km && (
                              <span className="font-mono text-xs ml-2.5" style={{ color: "var(--text-2)" }}>
                                {parseFloat(ts.distance_km).toFixed(0)} km
                              </span>
                            )}
                            {ts.stage_start_time && (
                              <span className="font-mono text-xs ml-2" style={{ color: "var(--text-3)" }}>
                                · Start {ts.stage_start_time.slice(0, 5)}
                              </span>
                            )}
                          </p>
                        </div>
                      ) : (
                        <div
                          className="rounded-xl px-4 py-3 mb-4"
                          style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
                        >
                          <p className="text-xs" style={{ color: "var(--text-3)" }}>Hviledag</p>
                        </div>
                      )}

                      {/* Progress bar */}
                      <div className="flex items-center gap-3">
                        <div
                          className="flex-1 h-[3px] rounded-full overflow-hidden"
                          style={{ background: "var(--surface-3)" }}
                        >
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{ width: `${pct}%`, background: "var(--accent)" }}
                          />
                        </div>
                        <span className="text-[11px] font-mono flex-shrink-0" style={{ color: "var(--text-3)" }}>
                          {race.completed_stages} / {race.total_stages} etaper
                        </span>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* ══ UPCOMING RACES ════════════════════════════════════════════════ */}
        {featuredRaces.length > 0 && (
          <section>
            <SectionHeader
              action={
                <Link href="/races" className="text-xs transition-colors hover:text-white" style={{ color: "var(--text-3)" }}>
                  Fuld kalender →
                </Link>
              }
            >
              Kommende løb
            </SectionHeader>

            <div className="rounded-2xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              {featuredRaces.map((race, i) => {
                const days = daysUntil(race.start_date);
                const imminent = days >= 0 && days <= 7;
                const isLast = i === featuredRaces.length - 1;

                return (
                  <Link
                    key={race.slug}
                    href={`/${race.slug}`}
                    className="group flex items-center gap-4 px-5 py-3.5 transition-colors duration-150 hover:bg-white/[0.03]"
                    style={{
                      borderBottom: isLast ? "none" : "1px solid var(--border)",
                    }}
                  >
                    <span className="text-lg w-7 text-center flex-shrink-0 leading-none">
                      {flagEmoji(race.country_code)}
                    </span>

                    <div className="flex-1 min-w-0">
                      <p
                        className="text-sm font-medium truncate transition-colors duration-150 group-hover:text-white"
                        style={{ color: "var(--foreground)" }}
                      >
                        {race.name}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[11px]" style={{ color: "var(--text-3)" }}>
                          {formatDate(race.start_date)}
                        </span>
                        {race.stage_count > 0 && (
                          <span
                            className="text-[10px] px-1.5 py-0.5 rounded"
                            style={{ color: "var(--text-3)", background: "var(--surface-2)" }}
                          >
                            {race.stage_count} etaper
                          </span>
                        )}
                        {race.startlist_count > 0 && (
                          <span
                            className="text-[10px] px-1.5 py-0.5 rounded"
                            style={{ color: "var(--text-3)", background: "var(--surface-2)" }}
                          >
                            {race.startlist_count} ryttere
                          </span>
                        )}
                      </div>
                    </div>

                    {days >= 0 && (
                      <span
                        className="text-[11px] font-mono px-2.5 py-1 rounded-lg flex-shrink-0"
                        style={{
                          background: imminent ? "var(--accent-dim)" : "var(--surface-2)",
                          color: imminent ? "var(--accent)" : "var(--text-3)",
                          border: imminent
                            ? "1px solid var(--accent-border)"
                            : "1px solid var(--border-subtle)",
                        }}
                      >
                        {days === 0 ? "I dag" : days === 1 ? "I morgen" : `om ${days}d`}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* ══ LATEST NEWS ══════════════════════════════════════════════════ */}
        {articles.length > 0 && (
          <section>
            <SectionHeader
              action={
                <Link href="/nyheder" className="text-xs transition-colors hover:text-white" style={{ color: "var(--text-3)" }}>
                  Alle nyheder →
                </Link>
              }
            >
              Seneste nyheder
            </SectionHeader>

            <div className="grid gap-4 sm:grid-cols-2">
              {articles.map((article, i) => {
                const catColor = CATEGORY_COLORS[article.category] ?? "var(--accent)";
                const catLabel = CATEGORY_LABELS[article.category] ?? article.category;
                const catGradient = CATEGORY_GRADIENT[article.category] ?? "from-slate-900 to-slate-950";
                const isLarge = i === 0;

                return (
                  <Link
                    key={article.slug}
                    href={`/nyheder/${article.slug}`}
                    className={`group relative overflow-hidden rounded-2xl transition-all duration-200 border border-white/[0.07] hover:border-white/[0.13] ${isLarge ? "sm:col-span-2" : ""}`}
                  >
                    <div className={`relative w-full overflow-hidden ${isLarge ? "h-64 sm:h-80" : "h-52"}`}>
                      {article.image_url ? (
                        <>
                          <Image
                            src={article.image_url}
                            alt=""
                            fill
                            sizes={isLarge ? "(max-width: 640px) 100vw, 832px" : "(max-width: 640px) 100vw, 406px"}
                            className="object-cover object-top transition-transform duration-500 group-hover:scale-[1.03]"
                            priority={i === 0}
                          />
                          <div
                            className="absolute inset-0"
                            style={{ background: "linear-gradient(to top, rgba(6,9,26,0.96) 0%, rgba(6,9,26,0.5) 50%, rgba(6,9,26,0.05) 100%)" }}
                          />
                        </>
                      ) : (
                        <div className={`absolute inset-0 bg-gradient-to-br ${catGradient}`} />
                      )}

                      <div className="absolute inset-0 flex flex-col justify-end p-5">
                        <div className="flex items-center gap-2 mb-2.5">
                          <span
                            className="text-[10px] uppercase tracking-[0.18em] font-bold"
                            style={{ color: catColor }}
                          >
                            {catLabel}
                          </span>
                          {article.races && (
                            <span className="text-[10px]" style={{ color: "var(--text-3)" }}>
                              · {article.races.name}
                            </span>
                          )}
                        </div>
                        <h3
                          className={`font-display tracking-wide leading-tight text-white transition-colors duration-200 group-hover:text-white/85 ${
                            isLarge ? "text-2xl sm:text-3xl" : "text-xl"
                          }`}
                        >
                          {article.title}
                        </h3>
                        <p className="text-[11px] mt-2.5" style={{ color: "var(--text-3)" }}>
                          {formatArticleDate(article.published_at)}
                        </p>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* Empty state */}
        {ongoingRaces.length === 0 && featuredRaces.length === 0 && articles.length === 0 && (
          <div className="rounded-2xl p-16 text-center" style={{ border: "1px solid var(--border)" }}>
            <p className="text-sm" style={{ color: "var(--text-3)" }}>
              Opdateres løbende — start backend-serveren for at se data.
            </p>
          </div>
        )}

      </div>
    </div>
  );
}
