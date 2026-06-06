export const revalidate = 300;

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import StageMapLoader from "./StageMapLoader";
import ClimbProfile from "./ClimbProfile";
import { API_BASE } from "@/lib/api";

// ── Types ────────────────────────────────────────────────────────────────────

type Stage = {
  stage_number: number;
  name: string | null;
  date: string | null;
  distance_km: number | null;
  stage_type: string | null;
  start_location: string | null;
  finish_location: string | null;
  elevation_gain_m: number | null;
  profile_score: number | null;
  elevation_image_url: string | null;
  pcs_stage_url: string | null;
  description: string | null;
  finish_type: string | null;
  fun_facts: string[] | null;
  stage_start_time: string | null;
  route_points: [number, number][] | null;
};

type Race = { id: string; name: string; slug: string };

type StartlistEntry = {
  bib_number: number | null;
  is_gc_captain: boolean;
  is_sprint_captain: boolean;
  status: string;
  riders: {
    name: string;
    slug: string;
    nationality: string | null;
    speciality: string | null;
    date_of_birth: string | null;
    uci_ranking: number | null;
    photo_url: string | null;
    hometown_region: string | null;
    training_region: string | null;
  } | null;
  teams: { name: string; slug: string; country_code: string | null } | null;
};

type Climb = {
  id: string;
  name: string;
  km_from_start: number | null;
  length_km: number | null;
  elevation_m: number | null;
  avg_gradient: number | null;
  max_gradient: number | null;
  gradient_sections: { km: number; gradient: number }[] | null;
  profile_image_url: string | null;
  region: string | null;
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

type StageNav = { stage_number: number; stage_type: string | null; finish_location: string | null };

// ── Data fetching ─────────────────────────────────────────────────────────────

async function getAllStages(slug: string): Promise<StageNav[]> {
  try {
    const res = await fetch(
      `${API_BASE}/races/${slug}/stages`,
      { next: { revalidate: 300 } }
    );
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

async function getStageDetail(
  slug: string,
  n: string
): Promise<{ stage: Stage; race: Race } | null> {
  try {
    const res = await fetch(
      `${API_BASE}/races/${slug}/stages/${n}`,
      { next: { revalidate: 300 } }
    );
    const data = await res.json();
    if (data?.error) return null;
    return data;
  } catch {
    return null;
  }
}

async function getStartlist(slug: string): Promise<StartlistEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/startlist`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

async function getClimbs(slug: string, n: string): Promise<Climb[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/stages/${n}/climbs`, { next: { revalidate: 300 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

async function getBroadcast(slug: string): Promise<Broadcast[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/broadcast`, { next: { revalidate: 300 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

type StageResult = {
  position: number;
  time_seconds: number | null;
  time_gap_seconds: number | null;
  riders: { name: string; slug: string; nationality: string | null; photo_url: string | null } | null;
};

async function getStageResults(slug: string, n: string): Promise<StageResult[]> {
  try {
    const res = await fetch(`${API_BASE}/races/${slug}/stages/${n}/results?limit=3`, { next: { revalidate: 300 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}

async function geocodeCity(
  cityName: string
): Promise<[number, number] | null> {
  if (!cityName) return null;
  try {
    // Strip parenthetical qualifiers: "Pila (Gressan)" → "Pila"
    const query = cityName.replace(/\(.*\)/, "").trim();
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1`,
      {
        headers: { "User-Agent": "Klassementet/1.0 (jonasb408@gmail.com)" },
        next: { revalidate: 86400 }, // Cache 24 h
      }
    );
    const data = await res.json();
    if (data[0]) return [parseFloat(data[0].lat), parseFloat(data[0].lon)];
  } catch {}
  return null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5))
    .join("");
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr + "T00:00:00").toLocaleDateString("da-DK", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function calculateAge(dob: string): number {
  const birth = new Date(dob);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  if (
    today.getMonth() < birth.getMonth() ||
    (today.getMonth() === birth.getMonth() &&
      today.getDate() < birth.getDate())
  )
    age--;
  return age;
}

const STAGE_TYPE_CONFIG: Record<
  string,
  { label: string; color: string; bg: string; desc: string }
> = {
  flat: {
    label: "Flad",
    color: "text-emerald-400",
    bg: "bg-emerald-500/15 text-emerald-300",
    desc: "Sprinteretape – forventet massespurt",
  },
  hilly: {
    label: "Kuperet",
    color: "text-yellow-400",
    bg: "bg-yellow-500/15 text-yellow-300",
    desc: "Kuperet terræn – favorabel for puncheurs",
  },
  mountain: {
    label: "Bjerg",
    color: "text-red-400",
    bg: "bg-red-500/15 text-red-300",
    desc: "Bjergetape – klatterne overtager",
  },
  tt: {
    label: "Enkeltstart",
    color: "text-blue-400",
    bg: "bg-blue-500/15 text-blue-300",
    desc: "Enkeltstart – kronometer-specialister",
  },
  itt: {
    label: "Enkeltstart",
    color: "text-blue-400",
    bg: "bg-blue-500/15 text-blue-300",
    desc: "Enkeltstart – kronometer-specialister",
  },
  ttt: {
    label: "Holdtidskørsel",
    color: "text-blue-400",
    bg: "bg-blue-500/15 text-blue-300",
    desc: "Holdtidskørsel – holdene kører samlet mod uret",
  },
};

// Ryttere der passer til etapetypen
const STAGE_SPECIALISTS: Record<string, string[]> = {
  flat:     ["Sprinter", "Classics", "Puncheur"],
  hilly:    ["Classics", "Puncheur", "Climber", "All-rounder"],
  mountain: ["Climber", "GC", "All-rounder"],
  tt:       ["Time trialist", "GC", "All-rounder"],
  itt:      ["Time trialist", "GC", "All-rounder"],
  ttt:      ["All-rounder", "GC", "Climber"],
};

// Specialiteter der IKKE passer til en etapetype
const INCOMPATIBLE: Record<string, string[]> = {
  flat:     ["Climber", "GC"],
  mountain: ["Sprinter"],
  tt:       ["Sprinter", "Classics", "Puncheur"],
  itt:      ["Sprinter", "Classics", "Puncheur"],
  ttt:      ["Sprinter", "Classics", "Puncheur"],
};

function isCompatibleWithStage(speciality: string | null, stageType: string | null): boolean {
  if (!speciality || !stageType) return true;
  return !(INCOMPATIBLE[stageType] ?? []).includes(speciality);
}

function getRidersForStage(
  startlist: StartlistEntry[],
  stageType: string | null,
  climbs: Climb[]
): { riders: StartlistEntry[]; localSlugs: Set<string> } {
  const active = startlist.filter((e) => e.status === "active");

  // Find unikke regioner fra etapens stigninger
  const stageRegions = new Set(
    climbs.map((c) => c.region?.toLowerCase().trim()).filter((r): r is string => !!r)
  );

  // Lokale ryttere: region matcher + specialitet kompatibel med etapetypen
  const localSlugs = new Set<string>();
  if (stageRegions.size > 0) {
    for (const e of active) {
      const r = e.riders;
      if (!r) continue;
      const homeReg = (r.hometown_region ?? "").toLowerCase().trim();
      const trainReg = (r.training_region ?? "").toLowerCase().trim();
      const isLocal = (homeReg && stageRegions.has(homeReg)) || (trainReg && stageRegions.has(trainReg));
      if (isLocal && isCompatibleWithStage(r.speciality, stageType)) {
        localSlugs.add(r.slug);
      }
    }
  }

  const sortFn = (a: StartlistEntry, b: StartlistEntry) => {
    // 1. Lokale favoritter øverst
    const aLocal = localSlugs.has(a.riders?.slug ?? "") ? 0 : 1;
    const bLocal = localSlugs.has(b.riders?.slug ?? "") ? 0 : 1;
    if (aLocal !== bLocal) return aLocal - bLocal;
    // 2. UCI-rangering (lavest = bedst)
    const rankA = a.riders?.uci_ranking ?? 9999;
    const rankB = b.riders?.uci_ranking ?? 9999;
    if (rankA !== rankB) return rankA - rankB;
    // 3. Kaptajn-flag som tiebreaker
    const capA = (stageType === "flat" ? a.is_sprint_captain : a.is_gc_captain) ? 0 : 1;
    const capB = (stageType === "flat" ? b.is_sprint_captain : b.is_gc_captain) ? 0 : 1;
    return capA - capB;
  };

  // Kandidatpulje: lokale ryttere + specialister (eller alle hvis ikke nok specialister)
  const target = STAGE_SPECIALISTS[stageType ?? ""] ?? [];
  const specialists = active.filter(
    (e) => e.riders?.speciality && target.includes(e.riders.speciality)
  );
  const localEntries = active.filter((e) => localSlugs.has(e.riders?.slug ?? ""));
  const localSlugSet = localSlugs;
  const nonLocal = (specialists.length >= 4 ? specialists : active).filter(
    (e) => !localSlugSet.has(e.riders?.slug ?? "")
  );

  const combined = [...localEntries, ...nonLocal].sort(sortFn).slice(0, 16);
  return { riders: combined, localSlugs };
}

// ── Metadata ──────────────────────────────────────────────────────────────────

export async function generateMetadata(
  props: { params: Promise<{ slug: string; n: string }> }
): Promise<Metadata> {
  const { slug, n } = await props.params;
  const detail = await getStageDetail(slug, n);
  if (!detail) return { title: "Etape ikke fundet" };
  const { stage, race } = detail;
  const finish = stage.finish_location ?? "";
  const start = stage.start_location ?? "";
  const title = `Etape ${n}: ${start} — ${finish} | ${race.name}`;
  const desc = `Alt om etape ${n} i ${race.name}: højdeprofil, favoritter, kort og etapeinfo. ${stage.distance_km ? `${stage.distance_km} km.` : ""}`;
  return {
    title,
    description: desc,
    openGraph: {
      title: `${title} | Klassementet`,
      description: desc,
      images: stage.elevation_image_url ? [{ url: stage.elevation_image_url }] : [],
    },
  };
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function StagePage(props: {
  params: Promise<{ slug: string; n: string }>;
}) {
  const { slug, n } = await props.params;

  const result = await getStageDetail(slug, n);
  if (!result) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-20 text-center">
        <p className="text-slate-500">Etape ikke fundet.</p>
        <Link
          href={`/${slug}`}
          className="mt-4 inline-block text-sm text-emerald-400 hover:underline"
        >
          ← Tilbage til løbet
        </Link>
      </div>
    );
  }

  const { stage, race } = result;

  const [startlist, climbs, broadcastAll, allStages, stageResults] = await Promise.all([
    getStartlist(slug),
    getClimbs(slug, n),
    getBroadcast(slug),
    getAllStages(slug),
    getStageResults(slug, n),
  ]);

  const stageNum   = parseInt(n);
  const prevStage  = allStages.find((s) => s.stage_number === stageNum - 1) ?? null;
  const nextStage  = allStages.find((s) => s.stage_number === stageNum + 1) ?? null;

  // Filtrer broadcasts til denne etape (baseret på stage-dato)
  const stageBroadcasts = broadcastAll.filter((b) => {
    if (stage.date && b.broadcast_date === stage.date) return true;
    if (b.stage_number === parseInt(n)) return true;
    return false;
  });

  // Geocode start og finish parallelt (cached 24h)
  const [startCoords, finishCoords] = await Promise.all([
    stage.start_location ? geocodeCity(stage.start_location) : null,
    stage.finish_location ? geocodeCity(stage.finish_location) : null,
  ]);

  const typeConfig = stage.stage_type
    ? STAGE_TYPE_CONFIG[stage.stage_type]
    : null;
  const { riders: recommendedRiders, localSlugs } = getRidersForStage(startlist, stage.stage_type, climbs);
  const danishRiders = startlist.filter(
    (e) => e.riders?.nationality === "DK"
  );

  const showMap = startCoords && finishCoords;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      {/* Navigationsbar: tilbage + forrige/næste etape */}
      <div className="flex items-center justify-between mb-8 gap-2">
        <Link
          href={`/${slug}`}
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          {race.name}
        </Link>

        <div className="flex items-center gap-1">
          {prevStage ? (
            <Link
              href={`/${slug}/stage/${prevStage.stage_number}`}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-800 text-xs text-slate-400 hover:border-slate-600 hover:text-slate-200 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
              E{prevStage.stage_number}
            </Link>
          ) : <span className="w-14" />}

          <span className="text-xs text-slate-700 px-2">E{stage.stage_number}</span>

          {nextStage ? (
            <Link
              href={`/${slug}/stage/${nextStage.stage_number}`}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-800 text-xs text-slate-400 hover:border-slate-600 hover:text-slate-200 transition-colors"
            >
              E{nextStage.stage_number}
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </Link>
          ) : <span className="w-14" />}
        </div>
      </div>

      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-xs font-mono text-slate-600 bg-slate-900 px-2 py-1 rounded">
            E{stage.stage_number}
          </span>
          {typeConfig && (
            <span className={`text-xs font-semibold px-2 py-1 rounded ${typeConfig.bg}`}>
              {typeConfig.label}
            </span>
          )}
          {stage.distance_km && (
            <span className="text-xs text-slate-500 font-mono">
              {stage.distance_km} km
            </span>
          )}
        </div>

        <h1 className="font-display text-5xl sm:text-6xl tracking-wide leading-none text-white mb-2">
          {stage.start_location && stage.finish_location
            ? `${stage.start_location} — ${stage.finish_location}`
            : stage.name ?? `Etape ${stage.stage_number}`}
        </h1>

        {stage.date && (
          <p className="text-slate-500 text-sm capitalize">
            {formatDate(stage.date)}
          </p>
        )}

        {typeConfig && (
          <p className="text-slate-600 text-xs mt-1">{typeConfig.desc}</p>
        )}
      </header>

      {/* Etapevinder */}
      {stageResults.length > 0 && (
        <div className="mb-8 rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
          <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-800 bg-slate-900/60">
            <span className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium">Resultat</span>
          </div>
          <div className="divide-y divide-slate-800/60">
            {stageResults.map((r) => {
              const rider = r.riders;
              if (!rider) return null;
              const flag = rider.nationality?.length === 2
                ? rider.nationality.toUpperCase().split("").map((c: string) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)).join("")
                : "";
              const podiumColors: Record<number, string> = {
                1: "text-yellow-400 font-bold",
                2: "text-slate-300 font-semibold",
                3: "text-amber-600 font-semibold",
              };
              const gap = r.time_gap_seconds && r.time_gap_seconds > 0
                ? `+${Math.floor(r.time_gap_seconds / 60)}:${String(r.time_gap_seconds % 60).padStart(2, "0")}`
                : null;
              return (
                <div key={r.position} className="flex items-center gap-4 px-5 py-3">
                  <span className={`text-sm w-6 text-center flex-shrink-0 ${podiumColors[r.position] ?? "text-slate-500"}`}>
                    {r.position}.
                  </span>
                  {rider.photo_url && (
                    <div className="relative w-8 h-8 flex-shrink-0 opacity-90">
                      <Image src={rider.photo_url} alt="" fill sizes="32px" className="rounded-full object-cover object-top" />
                    </div>
                  )}
                  <span className="text-base flex-shrink-0">{flag}</span>
                  <Link
                    href={`/riders/${rider.slug}`}
                    className="flex-1 text-sm font-medium text-slate-200 hover:text-emerald-300 transition-colors truncate"
                  >
                    {rider.name}
                  </Link>
                  {gap && <span className="text-xs text-slate-500 font-mono flex-shrink-0">{gap}</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Højdeprofil + individuelle stigninger */}
      <ClimbProfile
        climbs={climbs}
        elevationImageUrl={stage.elevation_image_url}
      />

      {/* Etapeinfo */}
      {(stage.description || stage.fun_facts?.length || stage.stage_start_time) && (
        <div className="mb-8 rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
          {/* Header-bar */}
          <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-800 bg-slate-900/60">
            <span className="text-xs uppercase tracking-[0.2em] text-emerald-400 font-medium">
              Etapeinfo
            </span>
            {stage.finish_type && (
              <span className="text-xs text-slate-500 capitalize">
                · {stage.finish_type === "sprint" ? "Massespurt" :
                   stage.finish_type === "uphill" ? "Bjerg-finish" :
                   stage.finish_type === "cobblestone" ? "Brosten-finish" :
                   stage.finish_type === "tt" ? "Enkeltstart" :
                   stage.finish_type === "gravel" ? "Grus-finish" :
                   stage.finish_type === "circuit" ? "Rund bane" :
                   stage.finish_type}
              </span>
            )}
            {stage.stage_start_time && (
              <span className="ml-auto text-xs text-slate-400 font-mono">
                🕐 Start {stage.stage_start_time.slice(0, 5)} CET
              </span>
            )}
          </div>

          <div className="p-5 space-y-4">
            {/* Beskrivelse */}
            {stage.description && (
              <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-line">
                {stage.description}
              </div>
            )}

            {/* Fun facts */}
            {stage.fun_facts && stage.fun_facts.length > 0 && (
              <div>
                <p className="text-xs uppercase tracking-[0.15em] text-slate-500 mb-2">
                  Kendte detaljer
                </p>
                <ul className="space-y-1.5">
                  {stage.fun_facts.map((fact, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-400">
                      <span className="text-emerald-500 mt-0.5 flex-shrink-0">·</span>
                      <span>{fact}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TV / Streaming */}
      {stageBroadcasts.length > 0 && (
        <div className="mb-8 rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-800 bg-slate-900/60">
            <span className="text-sm">📺</span>
            <span className="text-xs uppercase tracking-[0.2em] text-slate-400 font-medium">Se det her</span>
          </div>
          <div className="p-4 space-y-2">
            {stageBroadcasts.map((b, i) => (
              <div key={i} className="flex items-center justify-between gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
                    b.broadcaster.includes("TV 2") ? "bg-blue-500/15 text-blue-300" :
                    b.broadcaster.includes("Eurosport") ? "bg-orange-500/15 text-orange-300" :
                    b.broadcaster.includes("GCN") ? "bg-yellow-500/15 text-yellow-300" :
                    b.broadcaster.includes("Kanal") || b.broadcaster.includes("HBO") ? "bg-purple-500/15 text-purple-300" :
                    "bg-slate-700 text-slate-300"
                  }`}>
                    {b.broadcaster}
                  </span>
                  {b.is_live && (
                    <span className="flex items-center gap-1 text-[10px] text-red-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                      LIVE
                    </span>
                  )}
                </div>
                <span className="text-slate-400 font-mono text-xs">
                  {b.start_time?.slice(0, 5)}
                  {b.end_time ? ` – ${b.end_time.slice(0, 5)}` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Kort + Stats */}
      <div className="grid gap-4 lg:grid-cols-[1fr_260px] mb-10">
        {/* Kort */}
        {showMap ? (
          <div className="rounded-xl overflow-hidden border border-slate-800">
            <StageMapLoader
              start={startCoords}
              finish={finishCoords}
              startName={stage.start_location ?? "Start"}
              finishName={stage.finish_location ?? "Mål"}
              routePoints={stage.route_points}
            />
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 flex items-center justify-center text-slate-600 text-sm" style={{ minHeight: "280px" }}>
            Kortdata ikke tilgængeligt
          </div>
        )}

        {/* Stats */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 space-y-3">
          <h3 className="font-display text-lg tracking-widest text-slate-500 uppercase">
            Etapedata
          </h3>
          <div className="space-y-2 text-sm">
            {stage.distance_km && (
              <div className="flex justify-between">
                <span className="text-slate-500">Distance</span>
                <span className="text-slate-200 font-mono">{stage.distance_km} km</span>
              </div>
            )}
            {stage.elevation_gain_m && (
              <div className="flex justify-between">
                <span className="text-slate-500">Højdemeter</span>
                <span className={`font-mono ${typeConfig?.color ?? "text-slate-200"}`}>
                  +{stage.elevation_gain_m.toLocaleString("da-DK")} m
                </span>
              </div>
            )}
            {stage.profile_score && (
              <div className="flex justify-between">
                <span className="text-slate-500">Profil-score</span>
                <span className="text-slate-200 font-mono">{stage.profile_score}</span>
              </div>
            )}
            {stage.start_location && (
              <div className="flex justify-between">
                <span className="text-slate-500">Start</span>
                <span className="text-slate-200">{stage.start_location}</span>
              </div>
            )}
            {stage.finish_location && (
              <div className="flex justify-between">
                <span className="text-slate-500">Mål</span>
                <span className="text-slate-200 font-medium">{stage.finish_location}</span>
              </div>
            )}
          </div>

          {stage.pcs_stage_url && (
            <a
              href={stage.pcs_stage_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 block text-center text-xs text-slate-600 hover:text-emerald-400 transition-colors border border-slate-800 rounded-lg py-2"
            >
              Fuld analyse på ProCyclingStats →
            </a>
          )}
        </div>
      </div>

      {/* Anbefalede ryttere */}
      {recommendedRiders.length > 0 && (
        <section className="mb-10">
          <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase mb-4">
            Favoritter til etapen
          </h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {recommendedRiders.map((entry) => {
              const rider = entry.riders;
              if (!rider) return null;
              const isDanish = rider.nationality === "DK";
              const isCaptain = entry.is_gc_captain || entry.is_sprint_captain;
              const isLocal = localSlugs.has(rider.slug);

              return (
                <Link
                  key={rider.slug}
                  href={`/riders/${rider.slug}`}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors hover:border-slate-600 ${
                    isDanish
                      ? "border-red-800/50 bg-red-950/20 hover:bg-red-950/30"
                      : isCaptain
                      ? "border-emerald-800/50 bg-emerald-950/20"
                      : "border-slate-800/60 bg-slate-900/30"
                  }`}
                >
                  {/* Foto eller flag */}
                  <div className="relative flex-shrink-0 w-10 h-10">
                    {rider.photo_url ? (
                      <Image
                        src={rider.photo_url}
                        alt={rider.name}
                        fill
                        sizes="40px"
                        className="rounded-full object-cover object-top bg-slate-800"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center text-lg">
                        {flagEmoji(rider.nationality)}
                      </div>
                    )}
                    {rider.nationality && (
                      <span className="absolute -bottom-0.5 -right-0.5 text-[10px] leading-none">
                        {flagEmoji(rider.nationality)}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={`text-sm font-medium truncate ${isDanish ? "text-red-200" : "text-slate-100"}`}>
                        {rider.name}
                      </span>
                      {isLocal && (
                        <span className="text-[10px] bg-amber-500/15 text-amber-400 px-1.5 py-0.5 rounded flex-shrink-0">
                          🏠 Lokal
                        </span>
                      )}
                      {isDanish && (
                        <span className="text-xs bg-red-500/20 text-red-300 px-1.5 py-0.5 rounded flex-shrink-0">
                          DK
                        </span>
                      )}
                      {entry.is_gc_captain && (
                        <span className="text-xs bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded flex-shrink-0">
                          GC
                        </span>
                      )}
                      {entry.is_sprint_captain && (
                        <span className="text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded flex-shrink-0">
                          Sprint
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {entry.teams?.name}
                      {rider.date_of_birth && (
                        <span className="ml-2 text-slate-600">
                          {calculateAge(rider.date_of_birth)} år
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-0.5 flex-shrink-0">
                    {rider.uci_ranking && (
                      <span className="text-xs font-mono text-slate-400">#{rider.uci_ranking}</span>
                    )}
                    {rider.speciality && (
                      <span className="text-[10px] text-slate-600 hidden sm:block">{rider.speciality}</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* Danske ryttere */}
      {danishRiders.length > 0 && (
        <section>
          <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase mb-4">
            Danske ryttere i feltet
          </h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {danishRiders.map((entry) => {
              const rider = entry.riders;
              if (!rider) return null;
              const isFavorite = recommendedRiders.some(
                (r) => r.riders?.slug === rider.slug
              );

              return (
                <Link
                  key={rider.slug}
                  href={`/riders/${rider.slug}`}
                  className="flex items-center gap-3 px-4 py-3 rounded-xl border border-red-800/40 bg-red-950/15 hover:border-red-700/50 hover:bg-red-950/25 transition-colors"
                >
                  <div className="relative flex-shrink-0 w-10 h-10">
                    {rider.photo_url ? (
                      <Image
                        src={rider.photo_url}
                        alt={rider.name}
                        fill
                        sizes="40px"
                        className="rounded-full object-cover object-top bg-slate-800"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-red-950/60 flex items-center justify-center text-lg">
                        🇩🇰
                      </div>
                    )}
                    <span className="absolute -bottom-0.5 -right-0.5 text-[10px] leading-none">🇩🇰</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-red-100 truncate">
                        {rider.name}
                      </span>
                      {isFavorite && (
                        <span className="text-xs bg-yellow-500/20 text-yellow-300 px-1.5 py-0.5 rounded flex-shrink-0">
                          Favorit
                        </span>
                      )}
                      {entry.is_gc_captain && (
                        <span className="text-xs bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded flex-shrink-0">
                          GC
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {entry.teams?.name}
                      {rider.date_of_birth && (
                        <span className="ml-2 text-slate-600">
                          {calculateAge(rider.date_of_birth)} år
                        </span>
                      )}
                    </div>
                  </div>
                  {rider.speciality && (
                    <span className="text-xs text-slate-600 flex-shrink-0 hidden sm:block">
                      {rider.speciality}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
