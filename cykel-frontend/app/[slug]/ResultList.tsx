import Link from "next/link";

/** Én placering i et etape-/løbsresultat, som API'et leverer den. */
export type ResultEntry = {
  position: number;
  time_seconds: number | null;
  time_gap_seconds: number | null;
  riders: {
    name: string;
    slug: string;
    nationality: string | null;
    photo_url: string | null;
  } | null;
};

const PODIUM: Record<number, string> = {
  1: "text-yellow-400 font-bold",
  2: "text-slate-300 font-semibold",
  3: "text-amber-600 font-semibold",
};

function flag(nationality: string | null): string {
  if (!nationality || nationality.length !== 2) return "";
  return nationality
    .toUpperCase()
    .split("")
    .map((c) => String.fromCodePoint(c.charCodeAt(0) + 0x1f1a5))
    .join("");
}

/** 80 → "+1:20", 3980 → "+1:06:20" */
function formatGap(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const minutes = String(m).padStart(h > 0 ? 2 : 1, "0");
  return `+${h > 0 ? `${h}:` : ""}${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

/** 20968 → "5:49:28" — vinderens samlede tid, kun sat på position 1. */
function formatTotal(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Resultatlisten, som den ser ud på BÅDE etapesiderne og et endagsløbs
 *  landingsside. Ét sted, fordi et endagsløb netop skal læses som en etape —
 *  to kopier af rækkemarkup ville før eller siden vise de to ting forskelligt
 *  (CLAUDE.md §6: samme information, samme sted, samme form).
 *
 *  `visTid` slås fra på endagsløb (ejerens beslutning 2026-10-18). I et
 *  endagsløb er placeringen det, læseren kommer efter — feltet kommer ind i
 *  grupper, og en kolonne med "+0:04" på otte af ti rækker fortæller ikke
 *  noget, den optager kun plads. I et etapeløb betyder tiden derimod noget
 *  for klassementet, og dér bliver den stående. */
export default function ResultList({
  entries,
  visTid = true,
}: {
  entries: ResultEntry[];
  visTid?: boolean;
}) {
  return (
    <div className="divide-y divide-slate-800/40">
      {entries.map((entry) => {
        const rider = entry.riders;
        if (!rider) return null;
        const gapSec = entry.time_gap_seconds ?? 0;
        const isTop3 = entry.position <= 3;
        return (
          <div
            key={entry.position}
            className={`flex items-center gap-3 px-5 py-2.5 ${isTop3 ? "bg-slate-900/30" : ""}`}
          >
            <span
              className={`text-sm w-6 text-right flex-shrink-0 font-mono ${PODIUM[entry.position] ?? "text-slate-600"}`}
            >
              {entry.position}.
            </span>
            <span className="text-sm flex-shrink-0">{flag(rider.nationality)}</span>
            <Link
              href={`/riders/${rider.slug}`}
              className={`flex-1 text-sm hover:text-emerald-300 transition-colors truncate ${
                isTop3 ? "font-semibold text-slate-100" : "text-slate-300"
              }`}
            >
              {rider.name}
            </Link>
            {!visTid ? null : gapSec > 0 ? (
              <span className="text-xs text-slate-500 font-mono flex-shrink-0">
                {formatGap(gapSec)}
              </span>
            ) : entry.position === 1 && entry.time_seconds ? (
              <span className="text-xs text-slate-500 font-mono flex-shrink-0">
                {formatTotal(entry.time_seconds)}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
