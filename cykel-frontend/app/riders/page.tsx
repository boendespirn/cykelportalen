export const revalidate = 3600;

import type { Metadata } from "next";
import Link from "next/link";
import { API_BASE } from "@/lib/api";

export const metadata: Metadata = {
  title: "Ryttere",
  description: "Find alle ryttere fra UCI WorldTour — nationalitet, speciale, UCI-ranking og hold.",
  alternates: { canonical: "/riders" },
  openGraph: {
    url: "/riders",
    title: "Ryttere | Klassementet",
    description: "Find alle ryttere fra UCI WorldTour — nationalitet, speciale, UCI-ranking og hold.",
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
};

type Rider = {
  name: string;
  slug: string;
  nationality: string | null;
  speciality: string | null;
  uci_ranking: number | null;
  teams: { name: string; slug: string } | null;
};

async function getRiders(): Promise<Rider[]> {
  try {
    const res = await fetch(`${API_BASE}/riders`, { next: { revalidate: 3600 } });
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

export default async function RidersPage() {
  const riders = await getRiders();

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-12">
        <p className="text-xs uppercase tracking-[0.25em] text-emerald-400 mb-4">UCI WorldTour</p>
        <h1 className="font-display text-7xl sm:text-9xl tracking-wide leading-none text-white">
          Ryttere
        </h1>
        <p className="mt-4 text-slate-400 text-sm">
          {riders.length > 0
            ? `${riders.length} professionelle ryttere.`
            : "Start backend-serveren for at hente rytterdata."}
        </p>
      </header>

      {riders.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 p-16 text-center text-slate-600 text-sm">
          Ingen ryttere fundet.
        </div>
      ) : (
        <div className="rounded-xl border border-slate-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900">
                <th className="text-left px-4 py-3 text-slate-500 font-medium w-16 hidden sm:table-cell">#</th>
                <th className="text-left px-4 py-3 text-slate-500 font-medium">Rytter</th>
                <th className="text-left px-4 py-3 text-slate-500 font-medium hidden md:table-cell">Hold</th>
                <th className="text-left px-4 py-3 text-slate-500 font-medium hidden lg:table-cell">Specialitet</th>
              </tr>
            </thead>
            <tbody>
              {riders.map((rider, i) => (
                <tr
                  key={rider.slug}
                  className="border-b border-slate-800/40 hover:bg-slate-900/60 transition-colors"
                >
                  <td className="px-4 py-3 text-slate-700 font-mono text-xs hidden sm:table-cell">
                    {rider.uci_ranking ?? i + 1}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/riders/${rider.slug}`}
                      className="flex items-center gap-2.5 hover:text-emerald-400 transition-colors"
                    >
                      <span className="text-base w-6 text-center leading-none flex-shrink-0">
                        {flagEmoji(rider.nationality)}
                      </span>
                      <span className="font-medium text-slate-200">{rider.name}</span>
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-400 hidden md:table-cell">
                    {rider.teams ? (
                      <Link
                        href={`/teams/${rider.teams.slug}`}
                        className="hover:text-slate-200 transition-colors truncate block max-w-[200px]"
                      >
                        {rider.teams.name}
                      </Link>
                    ) : (
                      <span className="text-slate-700">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell">
                    {rider.speciality ? (
                      <span className={`text-xs ${SPECIALITY_COLORS[rider.speciality] ?? "text-slate-400"}`}>
                        {rider.speciality}
                      </span>
                    ) : (
                      <span className="text-slate-700">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
