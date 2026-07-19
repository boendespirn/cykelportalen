"use client";

import Link from "next/link";
import { useState } from "react";

type Standing = {
  position: number | null;
  time_gap_seconds: number | null;
  points?: number | null;
  riders: {
    name: string;
    slug: string;
    nationality: string | null;
    photo_url: string | null;
    teams: { name: string; slug: string } | null;
  } | null;
};

type Props = {
  raceName: string;
  gcStandings: Standing[];
  pointsStandings: Standing[];
  mountainsStandings: Standing[];
  youthStandings: Standing[];
};

const JERSEYS = [
  { key: "gc",        label: "GC",     emoji: "🩷", color: "pink",   desc: "Samlet klassement" },
  { key: "points",    label: "Point",  emoji: "💜", color: "purple", desc: "Pointklassement" },
  { key: "mountains", label: "Bjerge", emoji: "💙", color: "blue",   desc: "Bjergklassement" },
  { key: "youth",     label: "Ungdom", emoji: "🤍", color: "slate",  desc: "Ungdomsklassement" },
] as const;

type JerseyKey = typeof JERSEYS[number]["key"];

const COLOR_MAP: Record<string, { tab: string; active: string; ring: string; text: string }> = {
  pink:   { tab: "hover:text-pink-400",   active: "text-pink-400 border-pink-500/40 bg-pink-500/5",   ring: "ring-pink-500/30",   text: "text-pink-400"   },
  purple: { tab: "hover:text-purple-400", active: "text-purple-400 border-purple-500/40 bg-purple-500/5", ring: "ring-purple-500/30", text: "text-purple-400" },
  blue:   { tab: "hover:text-blue-400",   active: "text-blue-400 border-blue-500/40 bg-blue-500/5",   ring: "ring-blue-500/30",   text: "text-blue-400"   },
  slate:  { tab: "hover:text-slate-200",  active: "text-slate-200 border-slate-500/40 bg-slate-500/5",  ring: "ring-slate-400/30",  text: "text-slate-300"  },
};

function formatGap(seconds: number | null): string {
  if (seconds === null || seconds === 0) return "Leder";
  const abs = Math.abs(seconds);
  if (abs < 60) return `+${abs}″`;
  const m = Math.floor(abs / 60), s = abs % 60;
  if (abs < 3600) return `+${m}:${String(s).padStart(2, "0")}`;
  const h = Math.floor(abs / 3600), rem = abs % 3600, mm = Math.floor(rem / 60);
  return `+${h}:${String(mm).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
}

function flagEmoji(code: string | null): string {
  if (!code || code.length !== 2) return "";
  return code.toUpperCase().split("").map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5)).join("");
}

function RiderRow({ entry, rank, isPoints }: { entry: Standing; rank: number; isPoints: boolean }) {
  const r = entry.riders;
  if (!r) return null;
  const isLeader = entry.position === 1;

  return (
    <Link
      href={`/riders/${r.slug}`}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors hover:bg-slate-800/60 ${isLeader ? "bg-slate-800/40" : ""}`}
    >
      {/* Rangtal */}
      <span className={`w-5 text-center text-xs font-mono flex-shrink-0 ${isLeader ? "text-slate-300 font-bold" : "text-slate-600"}`}>
        {rank}
      </span>

      {/* Flag (rytterfotos vises ikke — se LEG-001) */}
      <div className="relative flex-shrink-0 w-9 h-9">
        <div className="w-9 h-9 rounded-full bg-slate-800 flex items-center justify-center text-base">
          {flagEmoji(r.nationality)}
        </div>
      </div>

      {/* Navn + hold */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium truncate ${isLeader ? "text-white" : "text-slate-200"}`}>
          {r.name}
        </p>
        <p className="text-xs text-slate-500 truncate">{r.teams?.name}</p>
      </div>

      {/* Gap / Points */}
      <span className={`text-xs font-mono flex-shrink-0 ${isLeader ? "text-emerald-400 font-semibold" : "text-slate-500"}`}>
        {isPoints
          ? `${entry.points ?? 0} pt`
          : formatGap(entry.time_gap_seconds)}
      </span>
    </Link>
  );
}

export default function RaceFavorites({
  gcStandings, pointsStandings, mountainsStandings, youthStandings,
}: Props) {
  const [active, setActive] = useState<JerseyKey>("gc");

  const standingsMap: Record<JerseyKey, Standing[]> = {
    gc:        gcStandings,
    points:    pointsStandings,
    mountains: mountainsStandings,
    youth:     youthStandings,
  };

  const current = standingsMap[active].slice(0, 8);
  const jersey  = JERSEYS.find((j) => j.key === active)!;
  const colors  = COLOR_MAP[jersey.color];
  const isPoints = active === "points" || active === "mountains";

  if (gcStandings.length === 0 && pointsStandings.length === 0) return null;

  return (
    <section className="mb-8 rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
      {/* Jersey-tabs */}
      <div className="flex border-b border-slate-800">
        {JERSEYS.map((j) => {
          const c = COLOR_MAP[j.color];
          const isActive = active === j.key;
          const hasData  = standingsMap[j.key].length > 0;
          return (
            <button
              key={j.key}
              onClick={() => hasData && setActive(j.key)}
              disabled={!hasData}
              className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium transition-colors border-b-2 -mb-px
                ${isActive
                  ? `${c.text} border-current`
                  : `text-slate-500 border-transparent ${hasData ? c.tab : "opacity-30 cursor-not-allowed"}`
                }`}
            >
              <span>{j.emoji}</span>
              <span className="hidden sm:inline">{j.label}</span>
            </button>
          );
        })}
      </div>

      {/* Standings liste */}
      <div className="p-3">
        {current.length === 0 ? (
          <p className="text-center text-xs text-slate-600 py-4">Ingen data endnu</p>
        ) : (
          <div className="space-y-0.5">
            {current.map((entry, i) => (
              <RiderRow
                key={entry.riders?.slug ?? i}
                entry={entry}
                rank={entry.position ?? i + 1}
                isPoints={isPoints}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-slate-800 bg-slate-900/30">
        <p className="text-[10px] text-slate-600">{jersey.desc} · Top {current.length}</p>
      </div>
    </section>
  );
}
