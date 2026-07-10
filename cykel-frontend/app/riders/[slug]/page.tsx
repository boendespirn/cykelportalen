export const revalidate = 3600;

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "@/lib/api";
import { isHistoricRaceSlug } from "@/lib/historic-stage";
import CollapsibleList from "./CollapsibleList";

type Rider = {
  name: string;
  slug: string;
  nationality: string | null;
  date_of_birth: string | null;
  speciality: string | null;
  uci_ranking: number | null;
  source_url: string | null;
  photo_url: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  hometown: string | null;
  hometown_region: string | null;
  training_region: string | null;
  teams: { name: string; slug: string; country_code: string | null } | null;
};

type RiderRace = {
  bib_number: number | null;
  is_gc_captain: boolean;
  is_sprint_captain: boolean;
  races: {
    name: string;
    slug: string;
    start_date: string;
    end_date: string | null;
    country_code: string | null;
    category: string;
    race_type: string;
  } | null;
};

type StageWin = {
  stages: {
    stage_number: number;
    finish_location: string;
    date: string;
    races: { name: string; slug: string } | null;
  } | null;
};

type GcResult = {
  position: number;
  time_gap_seconds: number | null;
  after_stage_number: number;
  races: {
    name: string;
    slug: string;
    start_date: string;
    race_type: string | null;
  } | null;
};

type Palmares = {
  gc_results: GcResult[];
  stage_wins: StageWin[];
};

async function getRider(slug: string): Promise<Rider | null> {
  try {
    const res = await fetch(`${API_BASE}/riders/${slug}`, { next: { revalidate: 3600 } });
    const data = await res.json();
    return data?.error ? null : data;
  } catch { return null; }
}

async function getRiderRaces(slug: string): Promise<RiderRace[]> {
  try {
    const res = await fetch(`${API_BASE}/riders/${slug}/races`, { next: { revalidate: 3600 } });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

async function getStageWins(slug: string): Promise<StageWin[]> {
  try {
    const res = await fetch(`${API_BASE}/riders/${slug}/stage-wins`, { next: { revalidate: 3600 } });
    return res.ok ? res.json() : [];
  } catch { return []; }
}

async function getPalmares(slug: string): Promise<Palmares> {
  try {
    const res = await fetch(`${API_BASE}/riders/${slug}/palmares`, { next: { revalidate: 3600 } });
    if (!res.ok) return { gc_results: [], stage_wins: [] };
    return res.json();
  } catch { return { gc_results: [], stage_wins: [] }; }
}

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code.toUpperCase().split("").map((c) =>
    String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)
  ).join("");
}

function calculateAge(dob: string): number {
  const birth = new Date(dob);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  if (today.getMonth() < birth.getMonth() ||
    (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())) age--;
  return age;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr + "T00:00:00").toLocaleDateString("da-DK", {
    day: "numeric", month: "long", year: "numeric",
  });
}

function formatShortDate(dateStr: string): string {
  return new Date(dateStr + "T00:00:00").toLocaleDateString("da-DK", {
    day: "numeric", month: "short", year: "numeric",
  });
}

const SPECIALITY_COLORS: Record<string, string> = {
  Climber:         "bg-red-500/15 text-red-400 border-red-500/25",
  Sprinter:        "bg-blue-500/15 text-blue-400 border-blue-500/25",
  "Time trialist": "bg-yellow-500/15 text-yellow-400 border-yellow-500/25",
  Puncheur:        "bg-orange-500/15 text-orange-400 border-orange-500/25",
  "All-rounder":   "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  GC:              "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  Classics:        "bg-purple-500/15 text-purple-400 border-purple-500/25",
};

const SPECIALITY_ICONS: Record<string, string> = {
  Climber: "⛰",
  Sprinter: "⚡",
  "Time trialist": "🕐",
  Puncheur: "👊",
  "All-rounder": "★",
  GC: "🏆",
  Classics: "🏛",
};

function formatGap(secs: number | null): string {
  if (!secs || secs === 0) return "";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `+${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `+${m}:${String(s).padStart(2, "0")}`;
}

const PODIUM_STYLES: Record<number, string> = {
  1: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40",
  2: "bg-slate-400/20 text-slate-300 border-slate-400/40",
  3: "bg-orange-700/20 text-orange-400 border-orange-600/40",
};

function StatCell({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="bg-slate-900/60 px-5 py-4 border border-slate-800/60 rounded-xl">
      <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-1.5">{label}</p>
      <p className="text-slate-200 font-medium text-sm leading-snug">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

export async function generateMetadata(
  props: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  const { slug } = await props.params;
  const rider = await getRider(slug);
  if (!rider) return { title: "Rytter ikke fundet" };
  const profileLine = [
    rider.speciality,
    rider.teams?.name,
    rider.nationality ? `Nationalitet: ${rider.nationality}` : null,
  ].filter(Boolean).join(" · ");
  const description = `${rider.name} — ${profileLine}. Se ryttertal, resultater og karrierestatistik på Klassementet.`;
  return {
    title: rider.name,
    description,
    alternates: {
      canonical: `/riders/${slug}`,
      types: { "application/rss+xml": "https://klassementet.dk/api/rss" },
    },
    openGraph: {
      title: `${rider.name} | Klassementet`,
      description,
      url: `/riders/${slug}`,
      siteName: "Klassementet",
      locale: "da_DK",
      type: "profile",
      images: rider.photo_url ? [{ url: rider.photo_url }] : [],
    },
  };
}

export default async function RiderPage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = await props.params;
  const [rider, riderRaces, stageWins, palmares] = await Promise.all([
    getRider(slug),
    getRiderRaces(slug),
    getStageWins(slug),
    getPalmares(slug),
  ]);

  if (!rider) {
    notFound();
  }

  const specialityClass = rider.speciality && SPECIALITY_COLORS[rider.speciality]
    ? SPECIALITY_COLORS[rider.speciality]
    : "bg-slate-800 text-slate-300 border-slate-700";

  const today = new Date().toISOString().slice(0, 10);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Person",
    name: rider.name,
    jobTitle: rider.speciality ?? "Professionel cykelrytter",
    memberOf: rider.teams ? { "@type": "SportsTeam", name: rider.teams.name } : undefined,
    nationality: rider.nationality ?? undefined,
    image: rider.photo_url ?? undefined,
    url: `https://klassementet.dk/riders/${slug}`,
  };

  return (
    <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <Link
        href="/riders"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-8"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Alle ryttere
      </Link>

      {/* Hero: photo + name */}
      <div className="flex flex-col sm:flex-row gap-6 sm:gap-8 mb-8">
        {/* Photo */}
        <div className="flex-shrink-0">
          {rider.photo_url ? (
            <Image
              src={rider.photo_url}
              alt={rider.name}
              width={192}
              height={192}
              className="w-40 h-40 sm:w-48 sm:h-48 object-cover object-top rounded-2xl border border-slate-800 bg-slate-900"
              priority
            />
          ) : (
            <div className="w-40 h-40 sm:w-48 sm:h-48 rounded-2xl border border-slate-800 bg-slate-900 flex items-center justify-center">
              <span className="text-5xl">{flagEmoji(rider.nationality)}</span>
            </div>
          )}
        </div>

        {/* Name + badges */}
        <div className="flex flex-col justify-end">
          {rider.nationality && (
            <span className="text-2xl mb-2 block">{flagEmoji(rider.nationality)}</span>
          )}
          <h1 className="font-display text-4xl sm:text-5xl tracking-wide leading-none text-white mb-4">
            {rider.name}
          </h1>
          <div className="flex flex-wrap gap-2">
            {rider.speciality && (
              <span className={`inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-full border font-medium ${specialityClass}`}>
                <span>{SPECIALITY_ICONS[rider.speciality] ?? ""}</span>
                {rider.speciality}
              </span>
            )}
            {rider.uci_ranking && (
              <span className="text-sm px-3 py-1.5 rounded-full border border-slate-700 bg-slate-800 text-slate-300 font-mono">
                UCI #{rider.uci_ranking}
              </span>
            )}
            {rider.teams && (
              <Link
                href={`/teams/${rider.teams.slug}`}
                className="text-sm px-3 py-1.5 rounded-full border border-slate-700 bg-slate-800/60 text-slate-400 hover:text-emerald-400 hover:border-emerald-500/30 transition-colors"
              >
                {flagEmoji(rider.teams.country_code)} {rider.teams.name}
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 mb-8">
        {rider.date_of_birth && (
          <StatCell
            label="Alder"
            value={`${calculateAge(rider.date_of_birth)} år`}
            sub={formatDate(rider.date_of_birth)}
          />
        )}
        {rider.nationality && (
          <StatCell
            label="Nationalitet"
            value={<span>{flagEmoji(rider.nationality)} {rider.nationality}</span>}
          />
        )}
        {rider.height_cm && (
          <StatCell label="Højde" value={`${rider.height_cm} cm`} />
        )}
        {rider.weight_kg && (
          <StatCell label="Vægt" value={`${rider.weight_kg} kg`} />
        )}
        {rider.hometown && (
          <StatCell
            label="Fødeby"
            value={rider.hometown}
            sub={rider.hometown_region ?? undefined}
          />
        )}
        {rider.training_region && (
          <StatCell label="Træner i" value={rider.training_region} sub="estimeret" />
        )}
        {rider.source_url && (
          <div className="bg-slate-900/60 px-5 py-4 border border-slate-800/60 rounded-xl flex flex-col justify-between">
            <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-1.5">Profil</p>
            <a
              href={rider.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-emerald-400 hover:text-emerald-300 transition-colors"
            >
              ProCyclingStats →
            </a>
          </div>
        )}
      </div>

      {/* Palmares — GC results */}
      {palmares.gc_results.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
            Palmares — samlet klassement
          </h2>
          <CollapsibleList
            initialCount={8}
            items={palmares.gc_results.map((r, i) => {
              if (!r.races) return null;
              const year = r.races.start_date?.slice(0, 4);
              const podiumStyle = PODIUM_STYLES[r.position] ?? "bg-slate-800/60 text-slate-400 border-slate-700";
              const gap = formatGap(r.time_gap_seconds);
              return (
                <Link
                  key={i}
                  href={`/${r.races.slug}`}
                  className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-colors"
                >
                  <span className={`text-xs font-bold w-8 h-8 flex items-center justify-center rounded-lg border flex-shrink-0 ${podiumStyle}`}>
                    {r.position}.
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">{r.races.name}</p>
                    {gap && <p className="text-xs text-slate-600 font-mono">{gap}</p>}
                  </div>
                  <span className="text-xs text-slate-500 font-mono flex-shrink-0">{year}</span>
                </Link>
              );
            }).filter((el): el is React.ReactElement => el !== null)}
          />
        </section>
      )}

      {/* Etapesejre */}
      {(stageWins.length > 0 || palmares.stage_wins.length > 0) && (() => {
        // Flet 2026-sejre med historiske, undgå dubletter
        const allWins = [...stageWins, ...palmares.stage_wins].filter((w) => w.stages?.races);
        const seen = new Set<string>();
        const unique = allWins.filter((w) => {
          const key = `${w.stages?.races?.slug}-${w.stages?.stage_number}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        unique.sort((a, b) => (b.stages?.date ?? "").localeCompare(a.stages?.date ?? ""));
        if (unique.length === 0) return null;
        return (
          <section className="mb-8">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
              Etapesejre
            </h2>
            <CollapsibleList
              initialCount={8}
              className="space-y-2"
              items={unique.map((win, i) => {
                const s = win.stages;
                if (!s || !s.races) return null;
                const historic = isHistoricRaceSlug(s.races.slug);
                const inner = (
                  <>
                    <span className="text-emerald-400 font-mono font-bold text-sm w-8 flex-shrink-0">
                      E{s.stage_number}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-200 truncate">{s.races.name}</p>
                      {s.finish_location && <p className="text-xs text-slate-500 truncate">Mål: {s.finish_location}</p>}
                    </div>
                    <div className="text-right flex-shrink-0">
                      {s.date && <p className="text-xs text-slate-500 font-mono">{formatShortDate(s.date)}</p>}
                      <p className="text-[10px] text-emerald-400 font-semibold uppercase tracking-wider mt-0.5">1. plads</p>
                    </div>
                  </>
                );
                if (historic) {
                  return (
                    <div
                      key={i}
                      className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3"
                    >
                      {inner}
                    </div>
                  );
                }
                return (
                  <Link
                    key={i}
                    href={`/${s.races.slug}/stage/${s.stage_number}`}
                    className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-colors"
                  >
                    {inner}
                  </Link>
                );
              }).filter((el): el is React.ReactElement => el !== null)}
            />
          </section>
        );
      })()}

      {/* Race calendar */}
      {riderRaces.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
            Løbskalender 2026
          </h2>
          <div className="space-y-2">
            {riderRaces.map((entry, i) => {
              const race = entry.races;
              if (!race) return null;
              const isOngoing = race.start_date <= today && (!race.end_date || race.end_date >= today);
              const isPast = race.end_date ? race.end_date < today : race.start_date < today;
              const startDate = new Date(race.start_date + "T00:00:00").toLocaleDateString("da-DK", {
                day: "numeric", month: "short",
              });
              return (
                <Link
                  key={i}
                  href={`/${race.slug}`}
                  className={`flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors hover:border-emerald-500/30
                    ${isOngoing ? "border-emerald-500/30 bg-emerald-500/5" : "border-slate-800 bg-slate-900/40"}`}
                >
                  {race.country_code && (
                    <span className="text-lg flex-shrink-0">{flagEmoji(race.country_code)}</span>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium truncate ${isPast ? "text-slate-500" : "text-slate-200"}`}>
                      {race.name}
                    </p>
                    <p className="text-xs text-slate-600">{race.category}</p>
                  </div>
                  {isOngoing && (
                    <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/15 px-2 py-0.5 rounded-full flex-shrink-0">
                      Live
                    </span>
                  )}
                  {entry.is_gc_captain && !isOngoing && (
                    <span className="text-[10px] bg-emerald-500/15 text-emerald-400 px-1.5 py-0.5 rounded flex-shrink-0">GC</span>
                  )}
                  {entry.is_sprint_captain && !entry.is_gc_captain && !isOngoing && (
                    <span className="text-[10px] bg-blue-500/15 text-blue-400 px-1.5 py-0.5 rounded flex-shrink-0">Sprint</span>
                  )}
                  <span className={`text-xs font-mono flex-shrink-0 ${isPast ? "text-slate-700" : "text-slate-500"}`}>
                    {startDate}
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
