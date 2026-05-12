export const dynamic = "force-dynamic";

import Link from "next/link";
import { API_BASE } from "@/lib/api";
import SpoilerSection from "./SpoilerSection";
import DnfSection from "./DnfSection";

// ── Types ──────────────────────────────────────────────────────────────────

type Race = {
  name: string; slug: string; start_date: string; end_date: string | null;
  country_code: string | null; category: string; pcs_url: string | null;
};

type Stage = {
  stage_number: number; name: string | null; date: string | null;
  distance_km: number | null; stage_type: string | null;
  start_location: string | null; finish_location: string | null;
  elevation_gain_m: number | null; profile_score: number | null;
  elevation_image_url: string | null; pcs_stage_url: string | null;
};

type StartlistEntry = {
  bib_number: number | null; is_gc_captain: boolean; is_sprint_captain: boolean;
  status: string; role: string | null;
  riders: { name: string; slug: string; nationality: string | null; speciality: string | null; date_of_birth: string | null } | null;
  teams: { name: string; slug: string; country_code: string | null } | null;
};

type GCEntry = {
  position: number | null; time_gap_seconds: number | null;
  riders: { name: string; slug: string; nationality: string | null; speciality: string | null; teams: { name: string; slug: string } | null } | null;
};

type ClassifEntry = {
  position: number | null; time_gap_seconds: number | null; points: number | null;
  riders: { name: string; slug: string; nationality: string | null } | null;
};

type DnfEntry = {
  status: string; dnf_stage_number: number | null; bib_number: number | null;
  riders: { name: string; slug: string; nationality: string | null } | null;
  teams: { name: string; slug: string } | null;
};

// ── Fetchers ───────────────────────────────────────────────────────────────

async function getRace(slug: string): Promise<Race | null> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}`, { cache: "no-store" });
    const data = await res.json();
    return data?.error ? null : data;
  } catch { return null; }
}

async function getStages(slug: string): Promise<Stage[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/stages`, { cache: "no-store" });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

async function getStartlist(slug: string): Promise<StartlistEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/startlist`, { cache: "no-store" });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

async function getGC(slug: string): Promise<{ after_stage: number; standings: GCEntry[] } | null> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/gc`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    return Array.isArray(data) && data.length === 0 ? null : data;
  } catch { return null; }
}

async function getClassification(slug: string, type: string): Promise<ClassifEntry | null> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/classifications/${type}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    if (Array.isArray(data) && data.length === 0) return null;
    return data?.standings?.[0] ?? null;
  } catch { return null; }
}

async function getDnfs(slug: string): Promise<DnfEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/dnfs`, { cache: "no-store" });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code.toUpperCase().split("").map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)).join("");
}

function formatDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" });
}

function formatShortDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "short" });
}

function calculateAge(dob: string): number {
  const birth = new Date(dob);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  if (today.getMonth() < birth.getMonth() || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())) age--;
  return age;
}

function getToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function stageStatus(stageDate: string | null, today: string): "completed" | "today" | "upcoming" {
  if (!stageDate) return "upcoming";
  if (stageDate < today) return "completed";
  if (stageDate === today) return "today";
  return "upcoming";
}

function groupByTeam(entries: StartlistEntry[]): Map<string, StartlistEntry[]> {
  const map = new Map<string, StartlistEntry[]>();
  for (const e of entries) {
    const k = e.teams?.name ?? "Ukendt hold";
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(e);
  }
  return map;
}

const STAGE_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  flat:     { label: "Flad",        color: "text-emerald-400" },
  hilly:    { label: "Kuperet",     color: "text-yellow-400"  },
  mountain: { label: "Bjerg",       color: "text-red-400"     },
  tt:       { label: "Enkeltstart", color: "text-blue-400"    },
  itt:      { label: "Enkeltstart", color: "text-blue-400"    },
};

const SPECIALITY_ICON: Record<string, string> = {
  Climber:         "⛰️",
  Sprinter:        "⚡",
  "Time trialist": "⏱️",
  Puncheur:        "💥",
  "All-rounder":   "🔄",
  GC:              "🏆",
  Classics:        "🏛️",
};

// ── Page ───────────────────────────────────────────────────────────────────

export default async function RacePage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = await props.params;
  const today = getToday();

  const [race, stages, startlist, gcData, pointsLeader, mountainsLeader, youthLeader, dnfs] =
    await Promise.all([
      getRace(slug),
      getStages(slug),
      getStartlist(slug),
      getGC(slug),
      getClassification(slug, "points"),
      getClassification(slug, "mountains"),
      getClassification(slug, "youth"),
      getDnfs(slug),
    ]);

  if (!race) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-20 text-center">
        <p className="text-slate-500">Løb ikke fundet.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-emerald-400 hover:underline">← Tilbage</Link>
      </div>
    );
  }

  const isOngoing   = race.start_date <= today && (!race.end_date || race.end_date >= today);
  const completedStages = stages.filter((s) => stageStatus(s.date, today) === "completed");
  const todayStage  = stages.find((s) => stageStatus(s.date, today) === "today") ?? null;
  // Hero: vis i dag-etape, ellers næste kommende etape (bruges øverst på siden)
  const heroStage   = todayStage ?? stages.find((s) => stageStatus(s.date, today) === "upcoming") ?? null;
  const teamGroups  = groupByTeam(startlist.filter(e => e.status === "active"));
  const totalRiders = startlist.filter(e => e.status === "active").length;

  // Udvalgte ryttere
  const danishRiders = startlist.filter((e) => e.riders?.nationality === "DK" && e.status === "active");
  const gcFavorites  = startlist.filter((e) => e.is_gc_captain && e.status === "active").slice(0, 8);
  const topUCIRiders = startlist
    .filter((e) => e.status === "active" && !e.is_gc_captain && e.riders?.speciality)
    .slice(0, 6);

  const hasResults = gcData && gcData.standings.length > 0;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Alle løb
      </Link>

      {/* ── Header ── */}
      <header className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          {race.country_code && <span className="text-4xl">{flagEmoji(race.country_code)}</span>}
          <span className="text-xs uppercase tracking-[0.2em] text-emerald-400">{race.category}</span>
          {isOngoing && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-full">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              LIVE
            </span>
          )}
        </div>
        <h1 className="font-display text-5xl sm:text-7xl tracking-wide leading-none text-white mb-3">
          {race.name}
        </h1>
        <p className="text-slate-400 text-sm">
          {formatDate(race.start_date)}
          {race.end_date && race.end_date !== race.start_date && ` — ${formatDate(race.end_date)}`}
        </p>
        {race.pcs_url && (
          <a href={race.pcs_url} target="_blank" rel="noopener noreferrer"
            className="mt-2 inline-block text-xs text-slate-600 hover:text-emerald-400 transition-colors">
            ProCyclingStats →
          </a>
        )}
      </header>

      {/* ── Live status strip ── */}
      {isOngoing && stages.length > 0 && (
        <div className="mb-8 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-5 py-4 flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-2">
            <span className="font-display text-xl text-white">{completedStages.length}</span>
            <span className="text-xs text-slate-500">/ {stages.length} etaper afsluttet</span>
          </div>
          {todayStage && (
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/15 px-2 py-0.5 rounded-full flex-shrink-0">I dag</span>
              <span className="text-sm text-slate-300 truncate">
                E{todayStage.stage_number}
                {todayStage.stage_type && <span className={`ml-1.5 ${STAGE_TYPE_CONFIG[todayStage.stage_type]?.color ?? "text-slate-400"}`}>· {STAGE_TYPE_CONFIG[todayStage.stage_type]?.label}</span>}
                {todayStage.start_location && todayStage.finish_location && (
                  <span className="text-slate-500 ml-1.5">{todayStage.start_location} → {todayStage.finish_location}</span>
                )}
              </span>
            </div>
          )}
          <div className="w-full sm:w-40">
            <div className="h-1 rounded-full bg-slate-800 overflow-hidden">
              <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${Math.round((completedStages.length / stages.length) * 100)}%` }} />
            </div>
          </div>
        </div>
      )}

      {/* ── Hero: dagens / næste etapes højdeprofil ── */}
      {isOngoing && heroStage?.elevation_image_url && (
        <Link href={`/${race.slug}/stage/${heroStage.stage_number}`} className="block mb-8 group">
          <div className="rounded-2xl border border-slate-800 overflow-hidden hover:border-emerald-500/30 transition-colors">
            {/* Label */}
            <div className="flex items-center gap-3 px-5 pt-4 pb-3">
              {todayStage && todayStage.stage_number === heroStage.stage_number ? (
                <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/15 px-2.5 py-1 rounded-full">I dag</span>
              ) : (
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500 bg-slate-800 px-2.5 py-1 rounded-full">Næste etape</span>
              )}
              <span className="text-sm text-slate-400">
                Etape {heroStage.stage_number}
                {heroStage.stage_type && (
                  <span className={`ml-2 ${STAGE_TYPE_CONFIG[heroStage.stage_type]?.color ?? "text-slate-400"}`}>
                    · {STAGE_TYPE_CONFIG[heroStage.stage_type]?.label}
                  </span>
                )}
              </span>
              {heroStage.distance_km && (
                <span className="text-xs font-mono text-slate-600 ml-auto">{heroStage.distance_km} km</span>
              )}
            </div>

            {/* Højdeprofil — fuld bredde, ingen crop */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={heroStage.elevation_image_url}
              alt={`Højdeprofil etape ${heroStage.stage_number}`}
              className="w-full"
            />

            {/* Start → Mål */}
            {heroStage.start_location && heroStage.finish_location && (
              <div className="flex items-center gap-2 px-5 py-3 border-t border-slate-800">
                <span className="text-sm text-slate-400">{heroStage.start_location}</span>
                <svg className="w-4 h-4 text-slate-700 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                </svg>
                <span className="text-sm font-semibold text-slate-200 group-hover:text-emerald-400 transition-colors">
                  {heroStage.finish_location}
                </span>
                {heroStage.elevation_gain_m && (
                  <span className="ml-auto text-xs font-mono text-red-400">↑ {heroStage.elevation_gain_m.toLocaleString("da-DK")} m</span>
                )}
              </div>
            )}
          </div>
        </Link>
      )}

      {/* ── Spoiler-sektion (GC + trøjer) ── */}
      {hasResults && (
        <SpoilerSection
          afterStage={gcData!.after_stage}
          gcStandings={gcData!.standings}
          pointsLeader={pointsLeader}
          mountainsLeader={mountainsLeader}
          youthLeader={youthLeader}
        />
      )}

      {/* ── Udvalgte ryttere ── */}
      {(danishRiders.length > 0 || gcFavorites.length > 0) && (
        <div className="grid gap-6 sm:grid-cols-2 mb-10">

          {/* GC-favoritter */}
          {gcFavorites.length > 0 && (
            <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
              <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 mb-4">🏆 GC-favoritter</h2>
              <div className="space-y-2">
                {gcFavorites.map((entry) => {
                  const r = entry.riders;
                  if (!r) return null;
                  const gcEntry = gcData?.standings.find(g => g.riders?.slug === r.slug);
                  return (
                    <Link key={r.slug} href={`/riders/${r.slug}`}
                      className="flex items-center gap-2.5 hover:bg-slate-800/50 rounded-lg px-2 py-1.5 transition-colors -mx-2">
                      <span className="w-5 text-center text-sm flex-shrink-0">{flagEmoji(r.nationality)}</span>
                      <span className="flex-1 text-sm font-medium text-slate-200">{r.name}</span>
                      {gcEntry && gcEntry.position != null && (
                        <span className="text-xs font-mono text-pink-400">#{gcEntry.position}</span>
                      )}
                      {r.speciality && (
                        <span className="text-xs text-slate-600">{SPECIALITY_ICON[r.speciality] ?? ""}</span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {/* Danske ryttere */}
          {danishRiders.length > 0 && (
            <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
              <h2 className="text-xs uppercase tracking-[0.2em] text-red-400 mb-4">🇩🇰 Danskere i løbet</h2>
              <div className="space-y-2">
                {danishRiders.map((entry) => {
                  const r = entry.riders;
                  if (!r) return null;
                  const gcEntry = gcData?.standings.find(g => g.riders?.slug === r.slug);
                  return (
                    <Link key={r.slug} href={`/riders/${r.slug}`}
                      className="flex items-center gap-2.5 hover:bg-slate-800/50 rounded-lg px-2 py-1.5 transition-colors -mx-2">
                      <span className="text-sm">🇩🇰</span>
                      <span className="flex-1 text-sm font-medium text-slate-200">{r.name}</span>
                      {gcEntry && gcEntry.position != null && (
                        <span className="text-xs font-mono text-pink-400">#{gcEntry.position}</span>
                      )}
                      {entry.is_gc_captain && <span className="text-xs bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">GC</span>}
                      {entry.is_sprint_captain && <span className="text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded">Sprint</span>}
                      {r.speciality && !entry.is_gc_captain && !entry.is_sprint_captain && (
                        <span className="text-xs text-slate-600">{SPECIALITY_ICON[r.speciality] ?? r.speciality}</span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      )}

      {/* ── Udgåede ryttere ── */}
      {dnfs.length > 0 && <DnfSection entries={dnfs} />}

      {/* ── Stats bar ── */}
      {totalRiders > 0 && (
        <div className="flex gap-6 mb-8 text-sm">
          <div><span className="text-2xl font-display tracking-wide text-white">{teamGroups.size}</span><span className="ml-1.5 text-slate-500">hold</span></div>
          <div><span className="text-2xl font-display tracking-wide text-white">{totalRiders}</span><span className="ml-1.5 text-slate-500">ryttere</span></div>
        </div>
      )}

      <div className="grid gap-10 lg:grid-cols-[1fr_340px]">

        {/* ── Startliste ── */}
        <section>
          <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase mb-5">
            Startliste {totalRiders > 0 && <span className="text-slate-700">({totalRiders})</span>}
          </h2>

          {startlist.length === 0 ? (
            <div className="rounded-xl border border-slate-800 p-10 text-center text-slate-600 text-sm">
              Startliste ikke tilgængelig endnu.
            </div>
          ) : (
            <div className="space-y-4">
              {[...teamGroups.entries()].map(([teamName, riders]) => {
                const team = riders[0]?.teams;
                const gcCaptain = riders.find(r => r.is_gc_captain);
                const sprintCaptain = riders.find(r => r.is_sprint_captain);
                return (
                  <div key={teamName} className="rounded-xl border border-slate-800 overflow-hidden">
                    <div className="bg-slate-900/80 px-4 py-3 flex items-center justify-between">
                      <Link href={team ? `/teams/${team.slug}` : "#"} className="flex items-center gap-2 hover:text-emerald-400 transition-colors">
                        {team?.country_code && <span className="text-base">{flagEmoji(team.country_code)}</span>}
                        <span className="font-semibold text-slate-200 text-sm">{teamName}</span>
                      </Link>
                      <span className="text-xs text-slate-600">{riders.length} ryttere</span>
                    </div>
                    {(gcCaptain || sprintCaptain) && (
                      <div className="px-4 py-2 bg-emerald-500/5 border-b border-slate-800 flex flex-wrap gap-2">
                        {gcCaptain?.riders && (
                          <Link href={`/riders/${gcCaptain.riders.slug}`}
                            className="flex items-center gap-1.5 text-xs bg-emerald-500/15 text-emerald-300 px-2.5 py-1 rounded-full hover:bg-emerald-500/25 transition-colors">
                            <span>🏆</span><span>{gcCaptain.riders.name}</span><span className="text-emerald-500 font-medium">GC</span>
                          </Link>
                        )}
                        {sprintCaptain?.riders && sprintCaptain.riders.slug !== gcCaptain?.riders?.slug && (
                          <Link href={`/riders/${sprintCaptain.riders.slug}`}
                            className="flex items-center gap-1.5 text-xs bg-blue-500/15 text-blue-300 px-2.5 py-1 rounded-full hover:bg-blue-500/25 transition-colors">
                            <span>⚡</span><span>{sprintCaptain.riders.name}</span><span className="text-blue-400 font-medium">Sprint</span>
                          </Link>
                        )}
                      </div>
                    )}
                    <div className="divide-y divide-slate-800/40">
                      {riders.map((entry) => {
                        const rider = entry.riders;
                        if (!rider) return null;
                        const isLeader = entry.is_gc_captain || entry.is_sprint_captain;
                        return (
                          <Link key={rider.slug} href={`/riders/${rider.slug}`}
                            className={`flex items-center gap-3 px-4 py-2.5 hover:bg-slate-900/60 transition-colors ${isLeader ? "bg-slate-900/30" : ""}`}>
                            {entry.bib_number && <span className="text-xs font-mono text-slate-700 w-6 text-right flex-shrink-0">{entry.bib_number}</span>}
                            <span className="text-sm flex-shrink-0 w-5 text-center">{flagEmoji(rider.nationality)}</span>
                            <span className={`flex-1 text-sm ${isLeader ? "text-slate-100 font-medium" : "text-slate-300"}`}>{rider.name}</span>
                            <div className="flex gap-1 flex-shrink-0">
                              {entry.is_gc_captain && <span className="text-xs bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded font-medium">GC</span>}
                              {entry.is_sprint_captain && <span className="text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded font-medium">Sprint</span>}
                            </div>
                            {rider.date_of_birth && (
                              <span className="text-xs text-slate-600 flex-shrink-0 hidden sm:block">{calculateAge(rider.date_of_birth)} år</span>
                            )}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* ── Sidebar: etaper ── */}
        <aside>
          <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase mb-5">
            Etaper {stages.length > 0 && <span className="text-slate-700">({stages.length})</span>}
          </h2>

          {stages.length === 0 ? (
            <div className="rounded-xl border border-slate-800 p-8 text-center text-slate-600 text-sm">Etapedata ikke tilgængelig endnu.</div>
          ) : (
            <div className="space-y-2">
              {stages.map((stage) => {
                const typeConfig = stage.stage_type ? STAGE_TYPE_CONFIG[stage.stage_type] : null;
                const status = stageStatus(stage.date, today);
                const isCompleted = status === "completed";
                const isToday = status === "today";
                return (
                  <Link key={stage.stage_number} href={`/${race.slug}/stage/${stage.stage_number}`} className="block group">
                    <div className={`rounded-xl border overflow-hidden transition-colors ${
                      isToday     ? "border-emerald-500/40 bg-emerald-500/5 hover:border-emerald-500/60"
                      : isCompleted ? "border-slate-800/50 bg-slate-900/20 hover:border-slate-700/60"
                      :               "border-slate-800/80 bg-slate-900/40 hover:border-slate-700"
                    }`}>
                      {stage.elevation_image_url && (
                        <div className={`w-full bg-slate-950 border-b border-slate-800/60 relative ${isCompleted ? "opacity-50" : ""}`}>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={stage.elevation_image_url} alt="" className="w-full h-28 object-cover" />
                          {isCompleted && (
                            <div className="absolute inset-0 flex items-center justify-center">
                              <svg className="w-5 h-5 text-emerald-500 drop-shadow" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            </div>
                          )}
                        </div>
                      )}
                      <div className="px-3 py-2.5">
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-mono font-medium ${isCompleted ? "text-slate-700" : "text-slate-600"}`}>E{stage.stage_number}</span>
                            {isToday && <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/15 px-1.5 py-0.5 rounded-full">I dag</span>}
                            {isCompleted && !stage.elevation_image_url && (
                              <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            )}
                            {typeConfig && <span className={`text-xs font-medium ${isCompleted ? "text-slate-600" : typeConfig.color}`}>{typeConfig.label}</span>}
                          </div>
                          <span className={`text-xs ${isCompleted ? "text-slate-700" : "text-slate-600"}`}>{formatShortDate(stage.date)}</span>
                        </div>
                        {stage.start_location && stage.finish_location ? (
                          <p className={`text-sm leading-snug ${isCompleted ? "text-slate-500" : "text-slate-300"}`}>
                            {stage.start_location}<span className="text-slate-700 mx-1">→</span>
                            <span className={`font-medium ${isCompleted ? "text-slate-500" : "text-slate-200"}`}>{stage.finish_location}</span>
                          </p>
                        ) : stage.name ? (
                          <p className={`text-sm ${isCompleted ? "text-slate-500" : "text-slate-300"}`}>{stage.name}</p>
                        ) : null}
                        <div className="flex items-center gap-3 mt-1.5">
                          {stage.distance_km && <span className={`text-xs font-mono ${isCompleted ? "text-slate-700" : "text-slate-600"}`}>{stage.distance_km} km</span>}
                          {stage.elevation_gain_m && <span className={`text-xs font-mono ${isCompleted ? "text-slate-700" : (typeConfig?.color ?? "text-slate-600")}`}>↑ {stage.elevation_gain_m.toLocaleString("da-DK")} m</span>}
                        </div>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
