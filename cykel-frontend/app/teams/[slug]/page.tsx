export const dynamic = "force-dynamic";

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
};

type Rider = {
  name: string;
  slug: string;
  nationality: string | null;
  speciality: string | null;
  uci_ranking: number | null;
};

async function getTeam(slug: string): Promise<Team | null> {
  try {
    const res = await fetch(`${API_BASE}/teams/${slug}`, { cache: "no-store" });
    const data = await res.json();
    if (data?.error) return null;
    return data;
  } catch {
    return null;
  }
}

async function getRiders(slug: string): Promise<Rider[]> {
  try {
    const res = await fetch(`${API_BASE}/teams/${slug}/riders`, { cache: "no-store" });
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
  Climber: "text-red-400",
  Sprinter: "text-blue-400",
  "Time trialist": "text-yellow-400",
  Puncheur: "text-orange-400",
  "All-rounder": "text-emerald-400",
  GC: "text-emerald-400",
};

export default async function TeamPage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = await props.params;
  const team = await getTeam(slug);
  const riders = await getRiders(slug);

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

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/teams" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Alle hold
      </Link>

      <header className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          {team.country_code && (
            <span className="text-4xl">{flagEmoji(team.country_code)}</span>
          )}
          {team.category && (
            <span className="text-xs uppercase tracking-[0.2em] text-emerald-400">{team.category}</span>
          )}
        </div>
        <h1 className="font-display text-5xl sm:text-7xl tracking-wide leading-none text-white mb-3">
          {team.name}
        </h1>
        <div className="flex flex-wrap gap-3 mt-4 text-sm text-slate-400">
          {team.uci_team_code && <span className="font-mono">{team.uci_team_code}</span>}
          {team.founded_year && <span>Grundlagt {team.founded_year}</span>}
        </div>
      </header>

      {/* Riders */}
      <section>
        <h2 className="font-display text-2xl tracking-widest text-slate-500 uppercase mb-5">
          Ryttere <span className="text-slate-700">({riders.length})</span>
        </h2>

        {riders.length === 0 ? (
          <div className="rounded-xl border border-slate-800 p-10 text-center text-slate-600 text-sm">
            Ingen ryttere fundet.
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-900">
                  <th className="text-left px-4 py-3 text-slate-500 font-medium">Rytter</th>
                  <th className="text-left px-4 py-3 text-slate-500 font-medium hidden sm:table-cell">Specialitet</th>
                  <th className="text-right px-4 py-3 text-slate-500 font-medium hidden md:table-cell">UCI</th>
                </tr>
              </thead>
              <tbody>
                {riders.map((rider) => (
                  <tr key={rider.slug} className="border-b border-slate-800/50 hover:bg-slate-900/50 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/riders/${rider.slug}`} className="flex items-center gap-2 hover:text-emerald-400 transition-colors">
                        <span className="text-base w-6 text-center">{flagEmoji(rider.nationality)}</span>
                        <span className="font-medium text-slate-200">{rider.name}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      {rider.speciality ? (
                        <span className={`text-xs ${SPECIALITY_COLORS[rider.speciality] ?? "text-slate-400"}`}>
                          {rider.speciality}
                        </span>
                      ) : (
                        <span className="text-slate-700">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-slate-500 hidden md:table-cell">
                      {rider.uci_ranking ? `#${rider.uci_ranking}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
