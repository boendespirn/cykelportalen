export const revalidate = 3600;

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Team = {
  name: string;
  slug: string;
  country_code: string | null;
  category: string | null;
  uci_team_code: string | null;
  founded_year: number | null;
  website: string | null;
  description: string | null;
  history_text: string | null;
};

type Rider = {
  name: string;
  slug: string;
  nationality: string | null;
  speciality: string | null;
  uci_ranking: number | null;
  photo_url: string | null;
};

async function getTeam(slug: string): Promise<Team | null> {
  try {
    const res = await fetch(`${API_BASE}/teams/${slug}`, { next: { revalidate: 3600 } });
    const data = await res.json();
    if (data?.error) return null;
    return data;
  } catch {
    return null;
  }
}

async function getRiders(slug: string): Promise<Rider[]> {
  try {
    const res = await fetch(`${API_BASE}/teams/${slug}/riders`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5))
    .join("");
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

export async function generateMetadata(
  props: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  const { slug } = await props.params;
  const team = await getTeam(slug);
  if (!team) return { title: "Hold ikke fundet" };
  const description = team.description
    ? team.description.slice(0, 155)
    : `Alt om ${team.name} — ryttere, resultater og holdinfo fra UCI WorldTour.`;
  return {
    title: team.name,
    description,
    openGraph: {
      title: `${team.name} | Hold | Klassementet`,
      description,
    },
  };
}

export default async function TeamPage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = await props.params;
  const [team, riders] = await Promise.all([getTeam(slug), getRiders(slug)]);

  if (!team) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-20 text-center">
        <p className="text-slate-500">Hold ikke fundet.</p>
        <Link href="/teams" className="mt-4 inline-block text-sm text-emerald-400 hover:underline">
          ← Alle hold
        </Link>
      </div>
    );
  }

  const categoryLabel = team.category === "WorldTeam" ? "WT" : team.category === "ProTeam" ? "PT" : team.category;

  // Sort: GC captains first, then by UCI ranking
  const gcRiders = riders.filter(r => r.speciality === "GC" || r.speciality === "Climber" || r.speciality === "All-rounder");
  const otherRiders = riders.filter(r => !gcRiders.includes(r));
  const sortedRiders = [
    ...gcRiders.sort((a, b) => (a.uci_ranking ?? 9999) - (b.uci_ranking ?? 9999)),
    ...otherRiders.sort((a, b) => (a.uci_ranking ?? 9999) - (b.uci_ranking ?? 9999)),
  ];

  const teamDescription = team.description
    ? team.description.slice(0, 155)
    : `Alt om ${team.name} — ryttere, resultater og holdinfo fra UCI WorldTour.`;
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SportsOrganization",
    name: team.name,
    sport: "Cycling",
    url: team.website ?? `https://klassementet.dk/teams/${slug}`,
    foundingDate: team.founded_year?.toString(),
    description: teamDescription,
  };

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <Link href="/teams" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Alle hold
      </Link>

      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          {team.country_code && (
            <span className="text-4xl">{flagEmoji(team.country_code)}</span>
          )}
          {categoryLabel && (
            <span className="text-xs uppercase tracking-[0.2em] text-emerald-400 border border-emerald-500/30 rounded px-2 py-0.5">
              {categoryLabel}
            </span>
          )}
        </div>
        <h1 className="font-display text-5xl sm:text-7xl tracking-wide leading-none text-white mb-4">
          {team.name}
        </h1>
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-400">
          {team.uci_team_code && (
            <span className="font-mono text-slate-500">{team.uci_team_code}</span>
          )}
          {team.founded_year && (
            <span>Grundlagt {team.founded_year}</span>
          )}
          {team.website && (
            <a
              href={team.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-emerald-400 hover:underline"
            >
              {team.website.replace(/^https?:\/\//, "").replace(/\/$/, "")} →
            </a>
          )}
        </div>
      </header>

      {/* Team description / history */}
      {(team.description || team.history_text) && (
        <div className="mb-10 rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          {team.description && (
            <p className="text-slate-300 leading-relaxed text-sm mb-3">{team.description}</p>
          )}
          {team.history_text && (
            <p className="text-slate-400 leading-relaxed text-sm">{team.history_text}</p>
          )}
        </div>
      )}

      {/* Riders grid */}
      <section>
        <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase mb-5">
          Ryttere <span className="text-slate-700">({riders.length})</span>
        </h2>

        {riders.length === 0 ? (
          <div className="rounded-xl border border-slate-800 p-10 text-center text-slate-600 text-sm">
            Ingen ryttere fundet.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {sortedRiders.map((rider) => (
              <Link
                key={rider.slug}
                href={`/riders/${rider.slug}`}
                className="flex items-center gap-3 px-4 py-3 rounded-xl border border-slate-800/60 bg-slate-900/30 hover:border-slate-600 hover:bg-slate-900/60 transition-colors group"
              >
                {/* Photo or flag */}
                <div className="relative flex-shrink-0 w-12 h-12 rounded-full overflow-hidden border border-slate-700 bg-slate-800 flex items-center justify-center">
                  {rider.photo_url ? (
                    <Image
                      src={rider.photo_url}
                      alt={rider.name}
                      fill
                      sizes="48px"
                      className="object-cover object-top"
                    />
                  ) : (
                    <span className="text-xl">{flagEmoji(rider.nationality)}</span>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-200 group-hover:text-emerald-400 transition-colors truncate">
                    {rider.name}
                  </p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {rider.nationality && (
                      <span className="text-xs text-slate-600">{flagEmoji(rider.nationality)}</span>
                    )}
                    {rider.speciality && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${SPECIALITY_COLORS[rider.speciality] ?? "bg-slate-800 text-slate-400 border-slate-700"}`}>
                        {SPECIALITY_ICONS[rider.speciality] ?? ""} {rider.speciality}
                      </span>
                    )}
                  </div>
                </div>

                {/* UCI rank */}
                {rider.uci_ranking && (
                  <span className="flex-shrink-0 text-xs font-mono text-slate-600">
                    #{rider.uci_ranking}
                  </span>
                )}
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
