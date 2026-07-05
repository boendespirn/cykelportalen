"use client";
import { useState } from "react";
import ClassificationTabs, { type StandingEntry, getJerseyConfig } from "./ClassificationTabs";

type Props = {
  afterStage: number;
  gcStandings: StandingEntry[];
  pointsStandings: StandingEntry[];
  mountainsStandings: StandingEntry[];
  youthStandings: StandingEntry[];
  raceSlug?: string;
};

export default function SpoilerSection({
  afterStage,
  gcStandings,
  pointsStandings,
  mountainsStandings,
  youthStandings,
  raceSlug,
}: Props) {
  const [open, setOpen] = useState(false);
  const primaryJersey = getJerseyConfig(raceSlug)[0];

  return (
    <section className="mb-10">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between rounded-2xl border px-6 py-4 transition-all duration-200 ${
          open
            ? primaryJersey.openBg
            : `border-slate-700 bg-slate-900/60 ${primaryJersey.hoverBorder}`
        }`}
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl">🏆</span>
          <div className="text-left">
            <p className={`font-display tracking-widest text-sm uppercase ${primaryJersey.titleColor}`}>
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
        <div className="mt-3 animate-in fade-in duration-200">
          <ClassificationTabs
            gcStandings={gcStandings}
            pointsStandings={pointsStandings}
            mountainsStandings={mountainsStandings}
            youthStandings={youthStandings}
            raceSlug={raceSlug}
          />
        </div>
      )}
    </section>
  );
}
