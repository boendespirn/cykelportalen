export const revalidate = 60;

import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "@/lib/api";
import { isHistoricRaceSlug } from "@/lib/historic-stage";
import SpoilerSection from "./SpoilerSection";
import DnfSection from "./DnfSection";
import StageMapLoader from "./stage/[n]/StageMapLoader";

// ── Types ──────────────────────────────────────────────────────────────────

type Race = {
  name: string; slug: string; start_date: string; end_date: string | null;
  country_code: string | null; category: string; pcs_url: string | null;
  race_type: string; cover_image_url: string | null; description: string | null;
};

type Stage = {
  stage_number: number; name: string | null; date: string | null;
  distance_km: number | null; stage_type: string | null;
  start_location: string | null; finish_location: string | null;
  elevation_gain_m: number | null; profile_score: number | null;
  elevation_image_url: string | null; pcs_stage_url: string | null;
  stage_start_time: string | null;
};

type StartlistEntry = {
  bib_number: number | null; is_gc_captain: boolean; is_sprint_captain: boolean;
  status: string; role: string | null;
  riders: { name: string; slug: string; nationality: string | null; speciality: string | null; date_of_birth: string | null; uci_ranking: number | null; photo_url: string | null } | null;
  teams: { name: string; slug: string; country_code: string | null } | null;
};

type GCEntry = {
  position: number | null; time_gap_seconds: number | null;
  riders: { name: string; slug: string; nationality: string | null; speciality: string | null; photo_url: string | null; teams: { name: string; slug: string } | null } | null;
};

type ClassifEntry = {
  position: number | null; time_gap_seconds: number | null; points: number | null;
  riders: { name: string; slug: string; nationality: string | null; photo_url: string | null; teams: { name: string; slug: string } | null } | null;
};

type DnfEntry = {
  status: string; dnf_stage_number: number | null; bib_number: number | null;
  riders: { name: string; slug: string; nationality: string | null } | null;
  teams: { name: string; slug: string } | null;
};

type Broadcast = {
  stage_number: number | null;
  broadcast_date: string;
  start_time: string | null;
  end_time: string | null;
  broadcaster: string;
  stream_url: string | null;
  is_live: boolean;
  notes: string | null;
};

type HistoryEntry = {
  year: number;
  slug: string;
  start_date: string;
  winner: {
    position: number;
    riders: { name: string; slug: string; nationality: string | null } | null;
  } | null;
};

// ── Legacy URL-aliaser ─────────────────────────────────────────────────────
// Kendte "spøgelses-URL'er" Google har indekseret, som ikke matcher noget rigtigt
// løb i DB (fx en gammel/ekstern permalink-struktur). I stedet for blot at 404'e
// og miste den akkumulerede ranking, sender vi et permanent (308/301-ækvivalent)
// redirect videre til det aktuelt relevante løb — fundet dynamisk, så mappingen
// ikke skal vedligeholdes manuelt år for år.
const LEGACY_RACE_NAME_ALIASES: Record<string, string> = {
  "tour-de-france-løb": "Tour de France",
};

async function getAllRaces(): Promise<{ name: string; slug: string; start_date: string; end_date: string | null }[]> {
  try {
    const res = await fetch(`${API_BASE}/races`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

/** Finder det mest relevante løb med et givent navn: igangværende først, ellers næste kommende, ellers seneste afsluttede. */
async function resolveLegacyAliasTarget(raceName: string): Promise<string | null> {
  const races = await getAllRaces();
  const matches = races.filter((r) => r.name === raceName);
  if (matches.length === 0) return null;

  const today = getToday();
  const ongoing = matches.find((r) => r.start_date <= today && (!r.end_date || r.end_date >= today));
  if (ongoing) return ongoing.slug;

  const upcoming = matches
    .filter((r) => r.start_date > today)
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];
  if (upcoming) return upcoming.slug;

  const past = matches
    .filter((r) => r.end_date && r.end_date < today)
    .sort((a, b) => (b.end_date as string).localeCompare(a.end_date as string))[0];
  return past?.slug ?? null;
}

// ── Fetchers ───────────────────────────────────────────────────────────────

async function getRace(slug: string): Promise<Race | null> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}`, { next: { revalidate: 60 } });
    const data = await res.json();
    return data?.error ? null : data;
  } catch { return null; }
}

async function getStages(slug: string): Promise<Stage[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/stages`, { next: { revalidate: 60 } });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

async function getStartlist(slug: string): Promise<StartlistEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/startlist`, { next: { revalidate: 60 } });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

async function getGC(slug: string): Promise<{ after_stage: number; standings: GCEntry[] } | null> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/gc`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    const data = await res.json();
    return Array.isArray(data) && data.length === 0 ? null : data;
  } catch { return null; }
}

async function getClassification(slug: string, type: string): Promise<{ after_stage: number; standings: ClassifEntry[] } | null> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/classifications/${type}`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    const data = await res.json();
    if (Array.isArray(data) && data.length === 0) return null;
    return data?.standings?.length ? data : null;
  } catch { return null; }
}

async function getDnfs(slug: string): Promise<DnfEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/dnfs`, { next: { revalidate: 60 } });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

async function getBroadcast(slug: string): Promise<Broadcast[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/broadcast`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

async function getRaceHistory(slug: string): Promise<HistoryEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/history`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

type RaceArticle = {
  slug: string;
  title: string;
  category: string;
  published_at: string;
  image_url: string | null;
};

async function getRaceNews(slug: string): Promise<RaceArticle[]> {
  try {
    const res = await fetch(`${API_BASE}/news?advertorial=false&race_slug=${slug}&limit=6`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

async function geocodeCity(cityName: string): Promise<[number, number] | null> {
  if (!cityName) return null;
  try {
    const query = cityName.replace(/\(.*\)/, "").trim();
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1`,
      {
        headers: { "User-Agent": "Klassementet/1.0 (jonasb408@gmail.com)" },
        next: { revalidate: 86400 },
      }
    );
    const data = await res.json();
    if (data[0]) return [parseFloat(data[0].lat), parseFloat(data[0].lon)];
  } catch {}
  return null;
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

// ── Shared: Startlist block ────────────────────────────────────────────────

function StartlistBlock({
  teamGroups, totalRiders, gcData,
}: {
  teamGroups: Map<string, StartlistEntry[]>;
  totalRiders: number;
  gcData: { after_stage: number; standings: GCEntry[] } | null;
}) {
  return (
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
                const gcEntry = gcData?.standings.find(g => g.riders?.slug === rider.slug);
                return (
                  <Link key={rider.slug} href={`/riders/${rider.slug}`}
                    className={`flex items-center gap-3 px-4 py-2.5 hover:bg-slate-900/60 transition-colors ${isLeader ? "bg-slate-900/30" : ""}`}>
                    {entry.bib_number && <span className="text-xs font-mono text-slate-700 w-6 text-right flex-shrink-0">{entry.bib_number}</span>}
                    <span className="text-sm flex-shrink-0 w-5 text-center">{flagEmoji(rider.nationality)}</span>
                    <span className={`flex-1 text-sm ${isLeader ? "text-slate-100 font-medium" : "text-slate-300"}`}>{rider.name}</span>
                    <div className="flex gap-1 flex-shrink-0">
                      {entry.is_gc_captain && <span className="text-xs bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded font-medium">GC</span>}
                      {entry.is_sprint_captain && <span className="text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded font-medium">Sprint</span>}
                      {gcEntry?.position != null && <span className="text-xs font-mono text-pink-400">#{gcEntry.position}</span>}
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
  );
}

// ── Metadata ───────────────────────────────────────────────────────────────

export async function generateMetadata(
  props: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  const { slug: rawSlug } = await props.params;
  let slug = rawSlug;
  try {
    slug = decodeURIComponent(rawSlug);
  } catch {
    // Ugyldig procent-sekvens: behold rawSlug.
  }
  if (LEGACY_RACE_NAME_ALIASES[slug]) return { title: "Tour de France" };
  const [race, stages] = await Promise.all([getRace(slug), getStages(slug)]);
  if (!race) return { title: "Løb ikke fundet" };
  const year = race.start_date ? new Date(race.start_date + "T00:00:00").getFullYear() : "";
  const dateRange = race.start_date
    ? race.end_date && race.end_date !== race.start_date
      ? `${formatDate(race.start_date)} – ${formatDate(race.end_date)}`
      : formatDate(race.start_date)
    : null;
  const isOneDay = race.race_type === "oneday";
  const description = isOneDay
    ? `${race.name} ${year}${dateRange ? ` (${dateRange})` : ""}: favoritter, ruteinfo, højdeprofil og resultat fra dette enkeltdagsløb — se det hele på Klassementet.`
    : `${race.name} ${year}${dateRange ? ` (${dateRange})` : ""}: alle ${stages.length || ""} etaper med startliste, favoritter, højdeprofiler og klassement.`;
  return {
    title: `${race.name} ${year}`,
    description,
    alternates: {
      canonical: `/${slug}`,
      types: { "application/rss+xml": "https://klassementet.dk/api/rss" },
    },
    openGraph: {
      title: `${race.name} ${year} | Klassementet`,
      description,
      url: `/${slug}`,
      siteName: "Klassementet",
      locale: "da_DK",
      type: "website",
      images: race.cover_image_url ? [{ url: race.cover_image_url }] : [],
    },
  };
}

// ── Page ───────────────────────────────────────────────────────────────────

export default async function RacePage(props: { params: Promise<{ slug: string }> }) {
  const { slug: rawSlug } = await props.params;
  // Next.js 16 leverer params som det rå, procent-kodede segment (fx "l%C3%B8b")
  // i stedet for at afkode det selv — afkod derfor eksplicit før alt slug-brug.
  let slug = rawSlug;
  try {
    slug = decodeURIComponent(rawSlug);
  } catch {
    // Ugyldig procent-sekvens: behold rawSlug, matcher blot ingen kendte slugs/aliaser.
  }
  const today = getToday();

  const legacyRaceName = LEGACY_RACE_NAME_ALIASES[slug];
  if (legacyRaceName) {
    const target = await resolveLegacyAliasTarget(legacyRaceName);
    if (target) permanentRedirect(`/${target}`);
    notFound();
  }

  const [race, stages, startlist, gcData, pointsData, mountainsData, youthData, dnfs, broadcasts, history, raceNews] =
    await Promise.all([
      getRace(slug),
      getStages(slug),
      getStartlist(slug),
      getGC(slug),
      getClassification(slug, "points"),
      getClassification(slug, "mountains"),
      getClassification(slug, "youth"),
      getDnfs(slug),
      getBroadcast(slug),
      getRaceHistory(slug),
      getRaceNews(slug),
    ]);

  if (!race) {
    notFound();
  }

  const isOngoing   = race.start_date <= today && (!race.end_date || race.end_date >= today);
  const isOneDay    = race.race_type === "oneday";
  const singleStage = isOneDay && stages.length > 0 ? stages[0] : null;
  const completedStages = stages.filter((s) => stageStatus(s.date, today) === "completed");
  const todayStage  = stages.find((s) => stageStatus(s.date, today) === "today") ?? null;
  const heroStage   = todayStage ?? stages.find((s) => stageStatus(s.date, today) === "upcoming") ?? null;
  const teamGroups  = groupByTeam(startlist.filter(e => e.status === "active"));
  const totalRiders = startlist.filter(e => e.status === "active").length;

  const danishRiders = startlist.filter((e) => e.riders?.nationality === "DK" && e.status === "active");
  const GC_SPECIALITIES = new Set(["GC", "Climber", "All-rounder", "Puncheur"]);
  const gcFavorites = isOneDay
    ? startlist.filter((e) => e.status === "active" && (e.is_gc_captain || e.is_sprint_captain)).slice(0, 8)
    : startlist
        .filter((e) => e.status === "active" && (
          e.riders?.uci_ranking != null ||
          e.is_gc_captain ||
          GC_SPECIALITIES.has(e.riders?.speciality ?? "")
        ))
        .sort((a, b) => {
          const rankA = a.riders?.uci_ranking ?? 9999;
          const rankB = b.riders?.uci_ranking ?? 9999;
          if (rankA !== rankB) return rankA - rankB;
          if (a.is_gc_captain !== b.is_gc_captain) return a.is_gc_captain ? -1 : 1;
          const gcA = GC_SPECIALITIES.has(a.riders?.speciality ?? "") ? 0 : 1;
          const gcB = GC_SPECIALITIES.has(b.riders?.speciality ?? "") ? 0 : 1;
          return gcA - gcB;
        })
        .slice(0, 8);
  const hasResults   = gcData && gcData.standings.length > 0;

  // For one-day races: geocode start/finish if we have a stage
  let startCoords: [number, number] | null = null;
  let finishCoords: [number, number] | null = null;
  if (isOneDay && singleStage?.start_location && singleStage?.finish_location) {
    [startCoords, finishCoords] = await Promise.all([
      geocodeCity(singleStage.start_location),
      geocodeCity(singleStage.finish_location),
    ]);
  }

  // ── Shared header ──────────────────────────────────────────────────────
  const header = (
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
      {race.description && (
        <p className="mt-4 text-slate-400 text-sm leading-relaxed max-w-2xl">
          {race.description}
        </p>
      )}
      {race.pcs_url && (
        <a href={race.pcs_url} target="_blank" rel="noopener noreferrer"
          className="mt-3 inline-block text-xs text-slate-600 hover:text-emerald-400 transition-colors">
          ProCyclingStats →
        </a>
      )}
    </header>
  );

  // ── JSON-LD SportsEvent ────────────────────────────────────────────────
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SportsEvent",
    name: race.name,
    description: race.description ?? `${race.name}: etaper, ryttere, klassement og stigningsprofiler.`,
    sport: "Cycling",
    startDate: race.start_date,
    endDate: race.end_date ?? race.start_date,
    ...(race.cover_image_url ? { image: race.cover_image_url } : {}),
    location: {
      "@type": "Place",
      name: race.name,
      address: { "@type": "PostalAddress", addressCountry: race.country_code ?? "IT" },
    },
    url: `https://klassementet.dk/${race.slug}`,
    organizer: { "@type": "Organization", name: "UCI WorldTour", url: "https://www.uci.org" },
  };

  // ══════════════════════════════════════════════════════════════════════
  // ONE-DAY RACE LAYOUT
  // ══════════════════════════════════════════════════════════════════════
  if (isOneDay) {
    const typeConfig = singleStage?.stage_type ? STAGE_TYPE_CONFIG[singleStage.stage_type] : null;

    return (
      <div className="mx-auto max-w-5xl px-6 py-10">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Alle løb
        </Link>

        {header}

        {/* Race stats bar */}
        {singleStage && (
          <div className="flex flex-wrap items-center gap-4 mb-6 pb-6 border-b border-slate-800">
            {typeConfig && (
              <span className={`text-sm font-medium ${typeConfig.color}`}>{typeConfig.label}</span>
            )}
            {singleStage.distance_km && (
              <span className="text-sm font-mono text-slate-400">{singleStage.distance_km} km</span>
            )}
            {singleStage.elevation_gain_m && (
              <span className={`text-sm font-mono ${typeConfig?.color ?? "text-slate-400"}`}>
                ↑ {singleStage.elevation_gain_m.toLocaleString("da-DK")} m
              </span>
            )}
            {singleStage.start_location && singleStage.finish_location && (
              <span className="text-sm text-slate-400">
                {singleStage.start_location}
                <svg className="inline w-4 h-4 mx-1.5 text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                </svg>
                <span className="font-medium text-slate-200">{singleStage.finish_location}</span>
              </span>
            )}
            {singleStage.pcs_stage_url && (
              <a href={singleStage.pcs_stage_url} target="_blank" rel="noopener noreferrer"
                className="ml-auto text-xs text-slate-600 hover:text-emerald-400 transition-colors">
                PCS →
              </a>
            )}
          </div>
        )}

        {/* Elevation profile — full width, prominent */}
        {singleStage?.elevation_image_url && (
          <div className="mb-8 rounded-2xl overflow-hidden border border-slate-800">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={singleStage.elevation_image_url} alt="Højdeprofil" className="w-full" />
          </div>
        )}

        {/* Route map + startlist side by side */}
        <div className={`grid gap-8 mb-10 ${startCoords && finishCoords ? "lg:grid-cols-[1fr_420px]" : ""}`}>

          {/* Map */}
          {startCoords && finishCoords && singleStage && (
            <div className="rounded-xl overflow-hidden border border-slate-800" style={{ minHeight: "320px" }}>
              <StageMapLoader
                start={startCoords}
                finish={finishCoords}
                startName={singleStage.start_location ?? "Start"}
                finishName={singleStage.finish_location ?? "Mål"}
              />
            </div>
          )}

          {/* Startlist */}
          <section>
            <div className="flex items-baseline justify-between mb-5">
              <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase">
                Startliste
              </h2>
              {totalRiders > 0 && (
                <span className="text-slate-700 text-sm font-mono">{totalRiders} ryttere</span>
              )}
            </div>

            {startlist.length === 0 ? (
              <div className="rounded-xl border border-slate-800 p-10 text-center text-slate-600 text-sm">
                Startliste ikke tilgængelig endnu.
              </div>
            ) : (
              <StartlistBlock teamGroups={teamGroups} totalRiders={totalRiders} gcData={gcData} />
            )}
          </section>
        </div>

        {/* Danish riders & GC favorites */}
        {(danishRiders.length > 0 || gcFavorites.length > 0) && (
          <div className="grid gap-6 sm:grid-cols-2 mb-10">
            {gcFavorites.length > 0 && (
              <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
                <h2 className="text-xs uppercase tracking-[0.2em] text-emerald-400 mb-4">🏆 Favoritter</h2>
                <div className="space-y-2">
                  {gcFavorites.map((entry) => {
                    const r = entry.riders;
                    if (!r) return null;
                    return (
                      <Link key={r.slug} href={`/riders/${r.slug}`}
                        className="flex items-center gap-2.5 hover:bg-slate-800/50 rounded-lg px-2 py-1.5 transition-colors -mx-2">
                        <span className="w-5 text-center text-sm flex-shrink-0">{flagEmoji(r.nationality)}</span>
                        <span className="flex-1 text-sm font-medium text-slate-200">{r.name}</span>
                        {r.speciality && <span className="text-xs text-slate-600">{SPECIALITY_ICON[r.speciality] ?? ""}</span>}
                      </Link>
                    );
                  })}
                </div>
              </section>
            )}
            {danishRiders.length > 0 && (
              <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
                <h2 className="text-xs uppercase tracking-[0.2em] text-red-400 mb-4">🇩🇰 Danskere</h2>
                <div className="space-y-2">
                  {danishRiders.map((entry) => {
                    const r = entry.riders;
                    if (!r) return null;
                    return (
                      <Link key={r.slug} href={`/riders/${r.slug}`}
                        className="flex items-center gap-2.5 hover:bg-slate-800/50 rounded-lg px-2 py-1.5 transition-colors -mx-2">
                        <span className="text-sm">🇩🇰</span>
                        <span className="flex-1 text-sm font-medium text-slate-200">{r.name}</span>
                        {entry.is_gc_captain && <span className="text-xs bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">Favorit</span>}
                        {r.speciality && <span className="text-xs text-slate-600">{SPECIALITY_ICON[r.speciality] ?? ""}</span>}
                      </Link>
                    );
                  })}
                </div>
              </section>
            )}
          </div>
        )}

        {dnfs.length > 0 && <DnfSection entries={dnfs} />}
        {hasResults && (
          <SpoilerSection
            afterStage={gcData!.after_stage}
            gcStandings={gcData!.standings}
            pointsStandings={pointsData?.standings ?? []}
            mountainsStandings={mountainsData?.standings ?? []}
            youthStandings={youthData?.standings ?? []}
            raceSlug={slug}
          />
        )}
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════════════════
  // STAGE RACE LAYOUT
  // ══════════════════════════════════════════════════════════════════════

  // Names stored as "LASTNAME Firstname" — convert to { first: "Firstname", last: "Lastname" }
  function formatRiderName(raw: string): { first: string; last: string } {
    const parts = raw.trim().split(/\s+/);
    const first = parts[parts.length - 1];
    const last = parts.slice(0, -1).map(w =>
      w.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase()).join('-')
    ).join(' ');
    return { first, last };
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Alle løb
      </Link>

      {race.cover_image_url && (
        <div className="relative mb-8 -mx-6 sm:mx-0 rounded-none sm:rounded-2xl overflow-hidden border-y sm:border border-slate-800 h-64 sm:h-96">
          <Image
            src={race.cover_image_url}
            alt={`${race.name} rutekort`}
            fill
            sizes="(max-width: 896px) 100vw, 896px"
            className="object-cover"
            priority
          />
        </div>
      )}

      {header}

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

      {/* ── Hero elevation profile ── */}
      {isOngoing && heroStage?.elevation_image_url && (
        <Link href={`/${race.slug}/stage/${heroStage.stage_number}`} className="block mb-8 group">
          <div className="rounded-2xl border border-slate-800 overflow-hidden hover:border-emerald-500/30 transition-colors">
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
              <div className="ml-auto flex items-center gap-3">
                {heroStage.stage_start_time && (
                  <span className="text-xs font-mono text-emerald-400">
                    Start {heroStage.stage_start_time.slice(0, 5)}
                  </span>
                )}
                {heroStage.distance_km && (
                  <span className="text-xs font-mono text-slate-600">{heroStage.distance_km} km</span>
                )}
              </div>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={heroStage.elevation_image_url}
              alt={`Højdeprofil etape ${heroStage.stage_number}`}
              className="w-full"
            />
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

      {/* ── Fremhævede profiler ── */}
      {(() => {
        const featured = startlist
          .filter((e) => e.status === "active" && e.riders?.uci_ranking != null)
          .sort((a, b) => (a.riders!.uci_ranking ?? 9999) - (b.riders!.uci_ranking ?? 9999))
          .slice(0, 20);
        if (featured.length < 3) return null;
        return (
          <section className="mb-10">
            <h2 className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-4">Fremhævede profiler</h2>
            <div className="grid grid-cols-4 sm:grid-cols-5 lg:grid-cols-10 gap-3">
              {featured.map((entry) => {
                const r = entry.riders!;
                return (
                  <Link key={r.slug} href={`/riders/${r.slug}`}
                    className="group flex flex-col items-center gap-1.5 text-center">
                    <div className="relative w-full aspect-square rounded-xl overflow-hidden bg-slate-900 border border-slate-800 group-hover:border-slate-600 transition-colors">
                      {r.photo_url ? (
                        <Image src={r.photo_url} alt={r.name} fill sizes="(max-width: 896px) 20vw, 140px" className="object-cover object-top" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-2xl">
                          {flagEmoji(r.nationality)}
                        </div>
                      )}
                      <span className="absolute top-1 left-1 text-[10px] font-mono font-bold text-white/90 bg-black/50 px-1 rounded leading-4">
                        #{r.uci_ranking}
                      </span>
                    </div>
                    <div className="w-full">
                      {(() => { const n = formatRiderName(r.name); return (<>
                        <p className="text-[11px] font-medium text-slate-200 leading-tight truncate">{n.first}</p>
                        {n.last && <p className="text-[10px] text-slate-400 leading-tight truncate">{n.last}</p>}
                      </>); })()}
                      {r.speciality && (
                        <p className="text-[9px] text-slate-600 truncate">{r.speciality}</p>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })()}

      {/* ── Danskere i løbet ── */}
      {danishRiders.length > 0 && (() => {
        const active = danishRiders.filter(e => e.riders);
        if (active.length === 0) return null;
        return (
          <section className="mb-10">
            <h2 className="text-xs uppercase tracking-[0.2em] text-red-400 mb-4">🇩🇰 Danskere i løbet</h2>
            <div className="grid grid-cols-4 sm:grid-cols-5 lg:grid-cols-10 gap-3">
              {active.map((entry) => {
                const r = entry.riders!;
                const n = formatRiderName(r.name);
                return (
                  <Link key={r.slug} href={`/riders/${r.slug}`}
                    className="group flex flex-col items-center gap-1.5 text-center">
                    <div className="relative w-full aspect-square rounded-xl overflow-hidden bg-slate-900 border border-red-900/40 group-hover:border-red-700/40 transition-colors">
                      {r.photo_url ? (
                        <Image src={r.photo_url} alt={r.name} fill sizes="(max-width: 896px) 20vw, 140px" className="object-cover object-top" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-2xl">🇩🇰</div>
                      )}
                      {r.uci_ranking != null && (
                        <span className="absolute top-1 left-1 text-[10px] font-mono font-bold text-white/90 bg-black/50 px-1 rounded leading-4">
                          #{r.uci_ranking}
                        </span>
                      )}
                    </div>
                    <div className="w-full">
                      <p className="text-[11px] font-medium text-slate-200 leading-tight truncate">{n.first}</p>
                      {n.last && <p className="text-[10px] text-slate-400 leading-tight truncate">{n.last}</p>}
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })()}

      {/* ── TV / Streaming ── */}
      {broadcasts.length > 0 && (() => {
        const upcoming = broadcasts.filter((b) => b.broadcast_date >= today);
        if (upcoming.length === 0) return null;

        // Gruppér per kanal — vis næste udsendelse per kanal
        const byChannel = new Map<string, Broadcast>();
        for (const b of upcoming) {
          if (!byChannel.has(b.broadcaster)) byChannel.set(b.broadcaster, b);
        }
        const channels = Array.from(byChannel.values());

        function channelStyle(name: string) {
          if (name.includes("TV 2")) return "bg-blue-500/15 text-blue-300 border-blue-500/20";
          if (name.includes("Eurosport")) return "bg-orange-500/15 text-orange-300 border-orange-500/20";
          if (name.includes("GCN")) return "bg-yellow-500/15 text-yellow-300 border-yellow-500/20";
          if (name.includes("HBO")) return "bg-purple-500/15 text-purple-300 border-purple-500/20";
          if (name.includes("Discovery") || name.includes("Kanal 5")) return "bg-blue-400/15 text-blue-200 border-blue-400/20";
          return "bg-slate-700/50 text-slate-300 border-slate-600/30";
        }

        return (
          <div className="mb-8 rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-800 bg-slate-900/60">
              <span className="text-sm">📺</span>
              <span className="text-xs uppercase tracking-[0.2em] text-slate-400 font-medium">Se det her</span>
            </div>
            <div className="p-4 flex flex-wrap gap-3">
              {channels.map((b, i) => (
                <div key={i} className={`flex flex-col gap-1 rounded-xl border px-4 py-3 min-w-[140px] ${channelStyle(b.broadcaster)}`}>
                  <span className="text-xs font-bold">{b.broadcaster}</span>
                  <span className="font-mono text-sm font-semibold">{b.start_time?.slice(0, 5)}</span>
                  <span className="text-[10px] opacity-70">
                    {new Date(b.broadcast_date + "T00:00:00").toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" })}
                    {b.stage_number ? ` · E${b.stage_number}` : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* ── Spoiler-sektion (fuld klassementstabel) ── */}
      {hasResults && (
        <SpoilerSection
          afterStage={gcData!.after_stage}
          gcStandings={gcData!.standings}
          pointsStandings={pointsData?.standings ?? []}
          mountainsStandings={mountainsData?.standings ?? []}
          youthStandings={youthData?.standings ?? []}
          raceSlug={slug}
        />
      )}

      {dnfs.length > 0 && <DnfSection entries={dnfs} />}

      <div className="grid gap-10 lg:grid-cols-[1fr_340px]">

        {/* ── Startliste — 2. på mobil, venstre kolonne på desktop ── */}
        <section className="order-2 lg:order-1">
          <div className="flex items-baseline justify-between mb-5">
            <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase">
              Startliste {totalRiders > 0 && <span className="text-slate-700">({totalRiders})</span>}
            </h2>
            {totalRiders > 0 && (
              <div className="flex gap-4 text-sm">
                <span><span className="font-display text-white">{teamGroups.size}</span><span className="ml-1 text-slate-600">hold</span></span>
                <span><span className="font-display text-white">{totalRiders}</span><span className="ml-1 text-slate-600">ryttere</span></span>
              </div>
            )}
          </div>
          {startlist.length === 0 ? (
            <div className="rounded-xl border border-slate-800 p-10 text-center text-slate-600 text-sm">
              Startliste ikke tilgængelig endnu.
            </div>
          ) : (
            <StartlistBlock teamGroups={teamGroups} totalRiders={totalRiders} gcData={gcData} />
          )}
        </section>

        {/* ── Etaper — 1. på mobil, højre kolonne på desktop ── */}
        <aside className="order-1 lg:order-2">
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
                const historic = isHistoricRaceSlug(race.slug);
                // Historiske etaper linkes kun når de reelt er backfillet
                // (elevation_image_url sat af stage_pcs_agent.py, trin 2 i
                // race_prep_pipeline.py) — ellers linker vi til en 404, som
                // var præcis det, SEO-019 fjernede. Se samme signal i
                // api.py get_races() (ready_through_stage) for sitemap.ts.
                const linkable = !historic || !!stage.elevation_image_url;
                const cardClass = `rounded-xl border overflow-hidden transition-colors ${
                  isToday     ? "border-emerald-500/40 bg-emerald-500/5" + (linkable ? " hover:border-emerald-500/60" : "")
                  : isCompleted ? "border-slate-800/50 bg-slate-900/20" + (linkable ? " hover:border-slate-700/60" : "")
                  :               "border-slate-800/80 bg-slate-900/40" + (linkable ? " hover:border-slate-700" : "")
                }`;
                const card = (
                    <div className={cardClass}>
                      {stage.elevation_image_url && (
                        <div className={`relative w-full h-28 bg-slate-950 border-b border-slate-800/60 ${isCompleted ? "opacity-50" : ""}`}>
                          <Image src={stage.elevation_image_url} alt="" fill sizes="(max-width: 640px) 100vw, 33vw" className="object-cover" />
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
                );
                if (!linkable) {
                  return <div key={stage.stage_number}>{card}</div>;
                }
                return (
                  <Link key={stage.stage_number} href={`/${race.slug}/stage/${stage.stage_number}`} className="block group">
                    {card}
                  </Link>
                );
              })}
            </div>
          )}
        </aside>
      </div>

      {/* ── Historiske vindere ── */}
      {history.length > 0 && (
        <section className="mt-12 pt-10 border-t border-slate-800/60">
          <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase mb-6">
            Tidligere vindere
          </h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {history.map((h) => {
              const winner = h.winner?.riders;
              const nat = winner?.nationality;
              const flag = nat && nat.length === 2
                ? nat.toUpperCase().split("").map((c: string) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)).join("")
                : "";
              const winnerFirst = winner ? winner.name.split(" ").slice(-1)[0].charAt(0) + winner.name.split(" ").slice(-1)[0].slice(1).toLowerCase() : "";
              const winnerLast = winner ? winner.name.split(" ").slice(0, -1).join(" ").toLowerCase().replace(/\b\w/g, (c: string) => c.toUpperCase()) : "";
              return (
                <div
                  key={h.slug}
                  className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-colors"
                >
                  <Link href={`/${h.slug}`} className="font-mono text-slate-500 text-sm w-10 flex-shrink-0 hover:text-emerald-400 transition-colors">
                    {h.year}
                  </Link>
                  {winner ? (
                    <>
                      <span className="text-base flex-shrink-0">{flag}</span>
                      <Link
                        href={`/riders/${winner.slug}`}
                        className="flex-1 text-sm font-medium text-slate-200 hover:text-emerald-300 transition-colors truncate"
                      >
                        {winnerFirst} {winnerLast}
                      </Link>
                    </>
                  ) : (
                    <span className="flex-1 text-sm text-slate-600 italic">Ingen data</span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Nyheder & analyser ─────────────────────────────────────────── */}
      {raceNews.length > 0 && (
        <section className="mt-12">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xs uppercase tracking-[0.25em] text-slate-400 font-medium">
              Nyheder & analyser
            </h2>
            <Link
              href={`/nyheder`}
              className="text-xs text-slate-600 hover:text-emerald-400 transition-colors"
            >
              Alle nyheder →
            </Link>
          </div>
          <div className="space-y-2">
            {raceNews.map((article) => (
              <Link
                key={article.slug}
                href={`/nyheder/${article.slug}`}
                className="group flex items-center gap-4 rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3.5 hover:border-emerald-500/30 hover:bg-slate-900 transition-all duration-150"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-200 group-hover:text-emerald-400 transition-colors leading-snug truncate">
                    {article.title}
                  </p>
                  <p className="text-xs text-slate-600 mt-0.5">
                    {new Date(article.published_at).toLocaleDateString("da-DK", { day: "numeric", month: "short" })}
                  </p>
                </div>
                <svg
                  className="w-4 h-4 text-slate-700 group-hover:text-emerald-500 flex-shrink-0 transition-colors"
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
