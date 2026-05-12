export const dynamic = "force-dynamic";

import Link from "next/link";
import { API_BASE } from "@/lib/api";

type Rider = {
  name: string;
  slug: string;
  nationality: string | null;
  date_of_birth: string | null;
  speciality: string | null;
  uci_ranking: number | null;
  source_url: string | null;
  teams: {
    name: string;
    slug: string;
    country_code: string | null;
  } | null;
};

async function getRider(slug: string): Promise<Rider | null> {
  try {
    const res = await fetch(`${API_BASE}/riders/${slug}`, { cache: "no-store" });
    const data = await res.json();
    if (data?.error) return null;
    return data;
  } catch {
    return null;
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

function calculateAge(dob: string): number {
  const birth = new Date(dob);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  if (
    today.getMonth() < birth.getMonth() ||
    (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())
  ) {
    age--;
  }
  return age;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr + "T00:00:00").toLocaleDateString("da-DK", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

const SPECIALITY_COLORS: Record<string, string> = {
  Climber: "bg-red-500/10 text-red-400 border-red-500/20",
  Sprinter: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  "Time trialist": "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  Puncheur: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  "All-rounder": "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  GC: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

export default async function RiderPage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = await props.params;
  const rider = await getRider(slug);

  if (!rider) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 text-center">
        <p className="text-slate-500">Rytter ikke fundet.</p>
        <Link href="/riders" className="mt-4 inline-block text-sm text-emerald-400 hover:underline">
          ← Alle ryttere
        </Link>
      </div>
    );
  }

  const specialityClass =
    rider.speciality && SPECIALITY_COLORS[rider.speciality]
      ? SPECIALITY_COLORS[rider.speciality]
      : "bg-slate-800 text-slate-300 border-slate-700";

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Link
        href="/riders"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-emerald-400 transition-colors mb-10"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Alle ryttere
      </Link>

      {/* Header */}
      <header className="mb-10">
        {rider.nationality && (
          <span className="text-5xl mb-4 block">{flagEmoji(rider.nationality)}</span>
        )}
        <h1 className="font-display text-5xl sm:text-7xl tracking-wide leading-none text-white mb-4">
          {rider.name}
        </h1>
        <div className="flex flex-wrap gap-2 mt-4">
          {rider.speciality && (
            <span className={`text-sm px-3 py-1 rounded-full border ${specialityClass}`}>
              {rider.speciality}
            </span>
          )}
          {rider.uci_ranking && (
            <span className="text-sm px-3 py-1 rounded-full border border-slate-700 bg-slate-800 text-slate-300 font-mono">
              UCI #{rider.uci_ranking}
            </span>
          )}
        </div>
      </header>

      {/* Info grid */}
      <div className="grid gap-px sm:grid-cols-2 rounded-xl overflow-hidden border border-slate-800 mb-8">
        {rider.date_of_birth && (
          <div className="bg-slate-900/60 px-5 py-4">
            <p className="text-xs uppercase tracking-widest text-slate-600 mb-1">Fødselsdato</p>
            <p className="text-slate-200 font-medium">{formatDate(rider.date_of_birth)}</p>
            <p className="text-xs text-slate-500 mt-0.5">{calculateAge(rider.date_of_birth)} år</p>
          </div>
        )}
        {rider.nationality && (
          <div className="bg-slate-900/60 px-5 py-4">
            <p className="text-xs uppercase tracking-widest text-slate-600 mb-1">Nationalitet</p>
            <p className="text-slate-200 font-medium">
              {flagEmoji(rider.nationality)} {rider.nationality}
            </p>
          </div>
        )}
        {rider.teams && (
          <div className="bg-slate-900/60 px-5 py-4">
            <p className="text-xs uppercase tracking-widest text-slate-600 mb-1">Hold</p>
            <Link href={`/teams/${rider.teams.slug}`} className="text-emerald-400 hover:text-emerald-300 transition-colors font-medium">
              {rider.teams.name}
            </Link>
          </div>
        )}
        {rider.source_url && (
          <div className="bg-slate-900/60 px-5 py-4">
            <p className="text-xs uppercase tracking-widest text-slate-600 mb-1">Kilde</p>
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
    </div>
  );
}
