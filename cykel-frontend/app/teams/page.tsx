export const revalidate = 3600;

import type { Metadata } from "next";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

export const metadata: Metadata = {
  title: "Hold",
  description: "Find alle hold fra UCI WorldTour — kategori, nationalitet og UCI-holdkode.",
  alternates: { canonical: "/teams" },
};

type Team = {
  name: string;
  slug: string;
  country_code: string | null;
  category: string | null;
  uci_team_code: string | null;
};

async function getTeams(): Promise<Team[]> {
  try {
    const res = await fetch(`${API_BASE}/teams`, { next: { revalidate: 3600 } });
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

function isWorldTeam(cat: string | null): boolean {
  return cat === "WT" || cat === "WorldTeam";
}

export default async function TeamsPage() {
  const teams = await getTeams();
  const worldTeams = teams.filter((t) => isWorldTeam(t.category));
  const proTeams = teams.filter((t) => !isWorldTeam(t.category));

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-12">
        <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">Professionelle hold</p>
        <h1 className="font-display text-7xl sm:text-9xl tracking-wide leading-none text-white">
          Hold
        </h1>
        <p className="mt-4 text-slate-400 text-sm">
          {teams.length > 0 ? `${teams.length} hold fra UCI WorldTour og ProTeams.` : "Start backend-serveren for at hente holddata."}
        </p>
      </header>

      {teams.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 p-16 text-center text-slate-600 text-sm">
          Ingen holddata fundet.
        </div>
      ) : (
        <>
          <TeamSection title="UCI WorldTeams" teams={worldTeams} />
          {proTeams.length > 0 && <TeamSection title="ProTeams" teams={proTeams} />}
        </>
      )}
    </div>
  );
}

function TeamSection({ title, teams }: { title: string; teams: Team[] }) {
  if (teams.length === 0) return null;
  return (
    <section className="mb-12">
      <h2 className="font-display text-xl tracking-[0.2em] text-slate-600 uppercase mb-5">
        {title} <span className="text-slate-700 font-display">({teams.length})</span>
      </h2>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {teams.map((team) => (
          <Link
            key={team.slug}
            href={`/teams/${team.slug}`}
            className="group flex items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-900/40 px-4 py-3.5 hover:border-emerald-500/40 hover:bg-slate-900 transition-all duration-150"
          >
            <span className="text-xl flex-shrink-0 w-7 text-center leading-none">
              {flagEmoji(team.country_code)}
            </span>
            <span className="flex-1 font-medium text-slate-200 group-hover:text-emerald-400 transition-colors truncate text-sm">
              {team.name}
            </span>
            {team.uci_team_code && (
              <span className="text-xs font-mono text-slate-600 flex-shrink-0">
                {team.uci_team_code}
              </span>
            )}
          </Link>
        ))}
      </div>
    </section>
  );
}
