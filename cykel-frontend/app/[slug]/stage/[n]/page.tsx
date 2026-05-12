import Link from "next/link";
import StageMapLoader from "./StageMapLoader";
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
  } | null;
  teams: { name: string; slug: string; country_code: string | null } | null;
};

// ── Data fetching ─────────────────────────────────────────────────────────────

async function getStageDetail(
  slug: string,
  n: string
): Promise<{ stage: Stage; race: Race } | null> {
  try {
    const res = await fetch(
      `${API_BASE}/races/${slug}/stages/${n}`,
      { cache: "no-store" }
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
        headers: { "User-Agent": "Cykelportalen/1.0 (jonasb408@gmail.com)" },
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
};

// Ryttere der passer til etapetypen
const STAGE_SPECIALISTS: Record<string, string[]> = {
  flat:     ["Sprinter", "Classics", "Puncheur"],
  hilly:    ["Classics", "Puncheur", "Climber", "All-rounder"],
  mountain: ["Climber", "GC", "All-rounder"],
  tt:       ["Time trialist", "GC", "All-rounder"],
  itt:      ["Time trialist", "GC", "All-rounder"],
};

function getRidersForStage(
  startlist: StartlistEntry[],
  stageType: string | null
): StartlistEntry[] {
  if (!stageType) return [];

  // Prioritér specialitet-match hvis data er tilgængeligt
  const target = STAGE_SPECIALISTS[stageType] ?? [];
  const bySpeciality = startlist.filter(
    (e) => e.riders?.speciality && target.includes(e.riders.speciality)
  );

  if (bySpeciality.length >= 4) {
    return bySpeciality
      .sort((a, b) => {
        if (a.is_gc_captain !== b.is_gc_captain) return a.is_gc_captain ? -1 : 1;
        if (a.is_sprint_captain !== b.is_sprint_captain) return a.is_sprint_captain ? -1 : 1;
        return 0;
      })
      .slice(0, 16);
  }

  // Fallback: brug kaptajn-flags baseret på etapetype
  if (stageType === "mountain" || stageType === "tt" || stageType === "itt") {
    return startlist.filter((e) => e.is_gc_captain).slice(0, 16);
  }
  if (stageType === "flat") {
    return startlist
      .filter((e) => e.is_sprint_captain || e.is_gc_captain)
      .sort((a, b) => (a.is_sprint_captain ? -1 : 1))
      .slice(0, 16);
  }
  // hilly: begge kaptajntyper
  return startlist
    .filter((e) => e.is_gc_captain || e.is_sprint_captain)
    .slice(0, 16);
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
  const startlist = await getStartlist(slug);

  // Geocode start og finish parallelt (cached 24h)
  const [startCoords, finishCoords] = await Promise.all([
    stage.start_location ? geocodeCity(stage.start_location) : null,
    stage.finish_location ? geocodeCity(stage.finish_location) : null,
  ]);

  const typeConfig = stage.stage_type
    ? STAGE_TYPE_CONFIG[stage.stage_type]
    : null;
  const recommendedRiders = getRidersForStage(startlist, stage.stage_type);
  const danishRiders = startlist.filter(
    (e) => e.riders?.nationality === "DK"
  );

  const showMap = startCoords && finishCoords;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      {/* Tilbage */}
      <Link
        href={`/${slug}`}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-8"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15 19l-7-7 7-7"
          />
        </svg>
        {race.name}
      </Link>

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

      {/* Høydeprofil — stor */}
      {stage.elevation_image_url && (
        <div className="mb-6 rounded-xl overflow-hidden border border-slate-800 bg-slate-950">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={stage.elevation_image_url}
            alt={`Høydeprofil etape ${stage.stage_number}`}
            className="w-full"
          />
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
                  <span className="text-lg flex-shrink-0">{flagEmoji(rider.nationality)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={`text-sm font-medium truncate ${isDanish ? "text-red-200" : "text-slate-100"}`}>
                        {rider.name}
                      </span>
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
                  <span className="text-lg">🇩🇰</span>
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
