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
  riders: {
    name: string;
    slug: string;
    nationality: string | null;
    teams: { name: string; slug: string } | null;
  } | null;
};

type Props = {
  afterStage: number;
  gcStandings: GCEntry[];
  pointsStandings: ClassifEntry[];
  mountainsStandings: ClassifEntry[];
  youthStandings: ClassifEntry[];
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
  if (!secs || secs === 0) return "Leder";
  if (secs < 60) return `+${secs}″`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (secs < 3600) return `+${m}:${String(s).padStart(2, "0")}`;
  const h = Math.floor(secs / 3600);
  const rem = secs % 3600;
  return `+${h}:${String(Math.floor(rem / 60)).padStart(2, "0")}:${String(rem % 60).padStart(2, "0")}`;
}

const JERSEY_CONFIG = [
  {
    key: "gc",
    color: "text-pink-400 border-pink-500/30 bg-pink-500/10",
    activeRing: "ring-pink-500/50",
    label: "Maglia Rosa",
    tableLabel: "Samlet klassement",
    emoji: "🩷",
    valueLabel: "Tid",
    description: "Den lyserøde trøje gives til rytteren med den laveste samlede tid. Den er det ultimative symbol på sejr i Giro d'Italia.",
  },
  {
    key: "points",
    color: "text-purple-400 border-purple-500/30 bg-purple-500/10",
    activeRing: "ring-purple-500/50",
    label: "Ciclamino",
    tableLabel: "Point-klassement",
    emoji: "🟣",
    valueLabel: "Point",
    description: "Den blomsterfarvede trøje gives til rytteren med flest sprintpoints fra etapemål og mellemspurter.",
  },
  {
    key: "mountains",
    color: "text-blue-400 border-blue-500/30 bg-blue-500/10",
    activeRing: "ring-blue-500/50",
    label: "Maglia Azzurra",
    tableLabel: "Bjerg-klassement",
    emoji: "🔵",
    valueLabel: "Point",
    description: "Den blå bjergtrøje gives til rytteren med flest point fra kategoriserede stigninger i løbet.",
  },
  {
    key: "youth",
    color: "text-slate-200 border-slate-400/30 bg-slate-500/10",
    activeRing: "ring-slate-400/50",
    label: "Maglia Bianca",
    tableLabel: "Ungdomsklassement",
    emoji: "⬜",
    valueLabel: "Tid",
    description: "Den hvide trøje gives til den bedst placerede rytter under 26 år i det samlede klassement.",
  },
] as const;

export default function SpoilerSection({
  afterStage,
  gcStandings,
  pointsStandings,
  mountainsStandings,
  youthStandings,
}: Props) {
  const [open, setOpen] = useState(false);
  const [tooltip, setTooltip] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string>("gc");

  const standingsMap: Record<string, GCEntry[] | ClassifEntry[]> = {
    gc: gcStandings,
    points: pointsStandings,
    mountains: mountainsStandings,
    youth: youthStandings,
  };

  const leaders: Record<string, { name: string; slug: string; nationality: string | null } | null> = {
    gc: gcStandings[0]?.riders ?? null,
    points: pointsStandings[0]?.riders ?? null,
    mountains: mountainsStandings[0]?.riders ?? null,
    youth: youthStandings[0]?.riders ?? null,
  };

  const activeConfig = JERSEY_CONFIG.find((j) => j.key === activeKey)!;
  const activeStandings = standingsMap[activeKey] ?? [];
  const isTimeClassif = activeKey === "gc" || activeKey === "youth";

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
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="mt-3 space-y-4 animate-in fade-in duration-200">

          {/* Jersey cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {JERSEY_CONFIG.map(({ key, color, activeRing, label, emoji, description }) => {
              const leader = leaders[key];
              if (!leader) return null;
              const isActive = activeKey === key;
              return (
                <div key={key} className="relative group">
                  <button
                    onClick={() => { setTooltip(null); setActiveKey(key); }}
                    className={`w-full text-left rounded-xl border px-4 py-3 pr-7 transition-all duration-150 ${color}
                      ${isActive
                        ? `ring-2 ${activeRing} ring-offset-1 ring-offset-slate-950 opacity-100`
                        : "opacity-60 hover:opacity-90"
                      }`}
                  >
                    <p className="text-xs opacity-70 mb-1">{emoji} {label}</p>
                    <p className="text-sm font-semibold leading-tight">
                      {flagEmoji(leader.nationality)} {leader.name}
                    </p>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setTooltip(tooltip === key ? null : key); }}
                    className="absolute top-2 right-2 w-4 h-4 rounded-full bg-black/30 text-[9px] flex items-center justify-center hover:bg-black/50 transition-colors"
                    aria-label={`Info om ${label}`}
                  >
                    ?
                  </button>
                  <div
                    className={`pointer-events-none absolute bottom-full left-0 right-0 mb-2 z-20 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 text-xs text-slate-300 shadow-xl transition-all duration-150
                      ${tooltip === key
                        ? "opacity-100 visible"
                        : "opacity-0 invisible group-hover:opacity-100 group-hover:visible"
                      }`}
                  >
                    {description}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Classification table */}
          <div>
            <p className={`text-xs uppercase tracking-[0.2em] mb-3 ${activeConfig.color}`}>
              {activeConfig.tableLabel} — Top {activeStandings.length}
            </p>
            <div className="rounded-xl border border-slate-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900">
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium w-10">#</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium">Rytter</th>
                    <th className="text-left px-4 py-2.5 text-slate-500 font-medium hidden sm:table-cell">Hold</th>
                    <th className="text-right px-4 py-2.5 text-slate-500 font-medium">{activeConfig.valueLabel}</th>
                  </tr>
                </thead>
                <tbody>
                  {(activeStandings as Array<GCEntry | ClassifEntry>).map((entry, i) => {
                    const rider = entry.riders;
                    if (!rider) return null;
                    const isLeader = !entry.time_gap_seconds || entry.time_gap_seconds === 0;
                    const pts = "points" in entry ? entry.points : null;
                    const leaderColor = activeConfig.color.split(" ")[0];
                    return (
                      <tr key={rider.slug + i} className="border-b border-slate-800/40 hover:bg-slate-900/50 transition-colors">
                        <td className="px-4 py-3 text-slate-500 font-mono text-xs">{entry.position ?? i + 1}</td>
                        <td className="px-4 py-3">
                          <Link href={`/riders/${rider.slug}`} className={`flex items-center gap-2 hover:${leaderColor} transition-colors`}>
                            <span className="w-5 text-center text-sm">{flagEmoji(rider.nationality)}</span>
                            <span className={`font-medium ${isLeader && isTimeClassif ? leaderColor : "text-slate-200"}`}>
                              {rider.name}
                              {isLeader && isTimeClassif && (
                                <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full uppercase tracking-wide ${activeConfig.color}`}>
                                  Leder
                                </span>
                              )}
                            </span>
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-slate-500 text-xs hidden sm:table-cell truncate max-w-[160px]">
                          {rider.teams?.name ?? "—"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-xs">
                          {isTimeClassif ? (
                            isLeader
                              ? <span className={leaderColor}>+0:00</span>
                              : <span className="text-slate-400">{formatGap(entry.time_gap_seconds)}</span>
                          ) : (
                            <span className={pts ? "text-slate-200" : "text-slate-600"}>
                              {pts ?? "—"}
                            </span>
                          )}
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
