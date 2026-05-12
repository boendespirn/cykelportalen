"use client";
import { useState } from "react";
import Link from "next/link";

type GCEntry = {
  position: number | null;
  time_gap_seconds: number | null;
  riders: {
    name: string;
    slug: string;
    nationality: string | null;
    speciality: string | null;
    teams: { name: string; slug: string } | null;
  } | null;
};

type ClassifEntry = {
  position: number | null;
  time_gap_seconds: number | null;
  points: number | null;
  riders: { name: string; slug: string; nationality: string | null } | null;
};

type Props = {
  afterStage: number;
  gcStandings: GCEntry[];
  pointsLeader: ClassifEntry | null;
  mountainsLeader: ClassifEntry | null;
  youthLeader: ClassifEntry | null;
};

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5))
    .join("");
}

function formatGap(secs: number | null): string {
  if (!secs || secs === 0) return "Leader";
  if (secs < 60) return `+${secs}″`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (secs < 3600) return `+${m}:${String(s).padStart(2, "0")}`;
  const h = Math.floor(secs / 3600);
  const rem = secs % 3600;
  return `+${h}:${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
}

const JERSEY_CONFIG = [
  { key: "gc",        color: "text-pink-400  border-pink-500/30  bg-pink-500/10",  label: "Maglia Rosa",    emoji: "🩷" },
  { key: "points",    color: "text-purple-400 border-purple-500/30 bg-purple-500/10", label: "Ciclamino",   emoji: "🟣" },
  { key: "mountains", color: "text-blue-400  border-blue-500/30  bg-blue-500/10",  label: "Maglia Azzurra", emoji: "🔵" },
  { key: "youth",     color: "text-slate-200 border-slate-400/30  bg-slate-500/10", label: "Maglia Bianca",  emoji: "⬜" },
];

export default function SpoilerSection({ afterStage, gcStandings, pointsLeader, mountainsLeader, youthLeader }: Props) {
  const [open, setOpen] = useState(false);

  const jerseyLeaders: Record<string, ClassifEntry | null> = {
    gc: gcStandings[0] ? { position: 1, time_gap_seconds: 0, points: null, riders: gcStandings[0].riders ? { name: gcStandings[0].riders.name, slug: gcStandings[0].riders.slug, nationality: gcStandings[0].riders.nationality } : null } : null,
    points: pointsLeader,
    mountains: mountainsLeader,
    youth: youthLeader,
  };

  return (
    <section className="mb-10">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between rounded-2xl border px-6 py-4 transition-all duration-200 ${
          open
            ? "border-pink-500/40 bg-pink-500/5"
            : "border-slate-700 bg-slate-900/60 hover:border-pink-500/30"
        }`}
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl">🏆</span>
          <div className="text-left">
            <p className="font-display tracking-widest text-sm uppercase text-pink-400">
              Resultater — Etape {afterStage}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              {open ? "Klik for at skjule" : "Klik for at se klassement (spoiler!)"}
            </p>
          </div>
        </div>
        <svg
          className={`w-5 h-5 text-slate-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="mt-3 space-y-6 animate-in fade-in duration-200">

          {/* Jersey leaders */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {JERSEY_CONFIG.map(({ key, color, label, emoji }) => {
              const leader = jerseyLeaders[key];
              if (!leader?.riders) return (
                <div key={key} className={`rounded-xl border px-4 py-3 ${color}`}>
                  <p className="text-xs opacity-60 mb-1">{emoji} {label}</p>
                  <p className="text-sm text-slate-500">Ingen data</p>
                </div>
              );
              return (
                <Link key={key} href={`/riders/${leader.riders.slug}`}
                  className={`rounded-xl border px-4 py-3 hover:opacity-80 transition-opacity ${color}`}>
                  <p className="text-xs opacity-70 mb-1">{emoji} {label}</p>
                  <p className="text-sm font-semibold leading-tight">
                    {flagEmoji(leader.riders.nationality)} {leader.riders.name}
                  </p>
                </Link>
              );
            })}
          </div>

          {/* GC top 10 */}
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-pink-400 mb-3">
              Samlet klassement — Top 10
            </p>
            <div className="rounded-xl border border-slate-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900">
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium w-10">#</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Rytter</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium hidden sm:table-cell">Hold</th>
                    <th className="text-right px-4 py-2.5 text-slate-500 font-medium">Tid</th>
                  </tr>
                </thead>
                <tbody>
                  {gcStandings.map((entry, i) => {
                    const rider = entry.riders;
                    if (!rider) return null;
                    const isLeader = !entry.time_gap_seconds || entry.time_gap_seconds === 0;
                    return (
                      <tr key={rider.slug} className="border-b border-slate-800/40 hover:bg-slate-900/50 transition-colors">
                        <td className="px-4 py-3 text-slate-500 font-mono text-xs">{entry.position ?? i + 1}</td>
                        <td className="px-4 py-3">
                          <Link href={`/riders/${rider.slug}`} className="flex items-center gap-2 hover:text-pink-400 transition-colors">
                            <span className="w-5 text-center text-sm">{flagEmoji(rider.nationality)}</span>
                            <span className={`font-medium ${isLeader ? "text-pink-300" : "text-slate-200"}`}>
                              {rider.name}
                              {isLeader && <span className="ml-1.5 text-[10px] bg-pink-500/20 text-pink-400 px-1.5 py-0.5 rounded-full uppercase tracking-wide">Leder</span>}
                            </span>
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-slate-500 text-xs hidden sm:table-cell truncate max-w-[160px]">
                          {rider.teams?.name ?? "—"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-xs">
                          {isLeader
                            ? <span className="text-pink-400">+0:00</span>
                            : <span className="text-slate-400">{formatGap(entry.time_gap_seconds)}</span>
                          }
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
